#
# Copyright (c) 2025 Joris Vink <joris@sanctorum.se>
#
# Permission to use, copy, modify, and distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

import kore

import os
import time
import signal
import hashlib

SQL_GET_FLOCKS_WITH_TIME_LEFT = """
SELECT DISTINCT
    network_token
FROM
    networks, accounts
WHERE
    networks.network_owner = accounts.account_id AND
    accounts.account_time_left > EXTRACT(epoch FROM now()) AND
    networks.network_ambry_update != 0
ORDER BY
    network_token
"""

SQL_GET_CATHEDRALS = """
SELECT
    cathedral_ip, cathedral_port
FROM
    cathedrals
WHERE
    cathedral_shrouded = 't'
ORDER BY
    cathedral_ip, cathedral_port
"""

SQL_GET_DEVICES_PER_FLOCK = """
SELECT
    device_kek,
    device_cathedral_id,
    device_cathedral_key,
    device_pubkey,
    device_bw_limit
FROM
    devices
WHERE
    device_network_token = $1 AND device_approved = 't'
ORDER BY
    device_cathedral_id
"""

SQL_GET_XFLOCKS = """
SELECT
    xflock_src_token, xflock_dst_token
FROM
    xflocks
"""

class Sync:
    def allow(self, seccomp, name):
        try:
            seccomp.allow(name)
        except Exception as e:
            kore.log(kore.LOG_INFO, f"seccomp: {e}")

    def seccomp(self, seccomp):
        self.allow(seccomp, "mkdir")
        self.allow(seccomp, "mkdirat")
        self.allow(seccomp, "renameat")
        self.allow(seccomp, "rename")
        self.allow(seccomp, "unlink")
        self.allow(seccomp, "unlinkat")

    def configure(self, args):
        self.counter = 0
        self.settings_digest = None

        # path -> (sha256 digest, st_size, st_mtime_ns) of what we last wrote.
        self.written = {}

        kore.config.workers = 1
        #kore.config.seccomp_tracing = "yes"
        kore.config.pidfile = "/tmp/sync.pid"
        kore.config.tls_dhparam = "/usr/local/share/kore/ffdhe4096.pem"

        self.deployment = os.getenv("SYNC_DEPLOYMENT", "dev")
        kore.config.deployment = self.deployment

        self.shared_path = os.getenv(
            "SYNC_SHARED_PATH", default="shared"
        )

        self.settings_path = f"{self.shared_path}/settings-shroud.conf"

        if self.deployment != "dev":
            kore.privsep("worker",
                root=self.shared_path,
                runas="api",
                skip=["chroot"]
            )

        self.dbhost = os.getenv("DBHOST", default="/var/run/postgresql")
        kore.dbsetup("db", f"host={self.dbhost} dbname=accounts")
        kore.task_create(self.run())

    def config_reset(self):
        self.cfg = []

    def config(self, line):
        self.cfg.append(line)

    def is_current(self, path, digest):
        try:
            st = os.stat(path)
        except FileNotFoundError:
            return False

        cached = self.written.get(path)
        if cached is not None:
            if cached == (digest, st.st_size, st.st_mtime_ns):
                return True

        try:
            with open(path, "rb") as f:
                ondisk = hashlib.sha256(f.read()).digest()
        except OSError:
            return False

        if ondisk != digest:
            return False

        self.written[path] = (digest, st.st_size, st.st_mtime_ns)
        return True

    def write_if_changed(self, path, data, mode=None):
        digest = hashlib.sha256(data).digest()

        if self.is_current(path, digest):
            return False

        tmppath = f"{path}.tmp"

        if mode is None:
            fd = os.open(tmppath, os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
        else:
            fd = os.open(tmppath,
                os.O_CREAT | os.O_TRUNC | os.O_WRONLY, mode)

        with open(fd, "wb") as f:
            f.write(data)

        os.rename(tmppath, path)

        st = os.stat(path)
        self.written[path] = (digest, st.st_size, st.st_mtime_ns)

        return True

    def config_write(self, path):
        body = ("\n".join(self.cfg) + "\n").encode()
        digest = hashlib.sha256(body).hexdigest()

        if digest == self.settings_digest and os.path.exists(path):
            return False

        data = f"# settings {digest[:16]}\n".encode() + body

        try:
            changed = self.write_if_changed(path, data, mode=0o444)
            self.settings_digest = digest
            return changed
        except Exception as e:
            kore.log(kore.LOG_NOTICE, f"failed to write settings {e}")
            return False

    async def run(self):
        while True:
            try:
                kore.log(kore.LOG_INFO, f"sync {self.counter} started")

                self.config_reset()
                self.identities_written = 0

                flocks = await kore.dbquery("db", SQL_GET_FLOCKS_WITH_TIME_LEFT)
                for flock in flocks:
                    await self.flock_sync(flock)

                xflocks = await self.resolve_xflocks()
                for key in sorted(xflocks):
                    if xflocks[key] != 2:
                        continue
                    flock_a, flock_b = key
                    ambry = "/home/cathedral/shared/ambries/"
                    ambry += f"ambry-{flock_a}_{flock_b}"
                    self.config(f"xflock {flock_a} {flock_b} {ambry}")

                cathedrals = await kore.dbquery("db", SQL_GET_CATHEDRALS)
                for cathedral in cathedrals:
                    ip = cathedral["cathedral_ip"]
                    port = cathedral["cathedral_port"]
                    self.config(f"federate {ip} {port}")

                changed = self.config_write(self.settings_path)

                kore.log(kore.LOG_INFO,
                    f"sync {self.counter} completed "
                    f"(settings {'updated' if changed else 'unchanged'}, "
                    f"{self.identities_written} identities written)")
                self.counter = self.counter + 1
            except Exception as e:
                kore.log(kore.LOG_NOTICE, f"sync failed: {e}")

            await kore.suspend(30 * 1000)

    async def flock_sync(self, flock):
        token = flock["network_token"]

        devices = await kore.dbquery("db",
            SQL_GET_DEVICES_PER_FLOCK,
            params=[token]
        )

        self.config(f"flock {token} {{")

        path = f"{self.shared_path}/identities/flock-{token}"
        os.makedirs(path, exist_ok=True)

        for device in devices:
            kek = hex(int(device["device_kek"]))
            pubkey = device["device_pubkey"]
            limit = device["device_bw_limit"]
            cid = device["device_cathedral_id"]
            key = device["device_cathedral_key"]

            path = f"{self.shared_path}/identities/flock-{token}/{cid}.key"
            if self.write_if_changed(path, bytes.fromhex(key)):
                self.identities_written += 1

            if pubkey != "NO-KEY":
                path = f"{self.shared_path}/identities/flock-{token}/{cid}.pub"
                if self.write_if_changed(path, bytes.fromhex(pubkey)):
                    self.identities_written += 1

            self.config(f"\tallow {cid} spi {kek} {limit}")

        self.config(f"\tambry /home/cathedral/shared/ambries/ambry-{token}")
        self.config("}")

    async def resolve_xflocks(self):
        xflocks = {}

        res = await kore.dbquery("db", SQL_GET_XFLOCKS)

        for row in res:
            flock_a = int(row["xflock_src_token"], 16)
            flock_b = int(row["xflock_dst_token"], 16)

            if flock_b < flock_a:
                tmp = row["xflock_src_token"]
                flock_a = row["xflock_dst_token"]
                flock_b = tmp
            else:
                flock_a = row["xflock_src_token"]
                flock_b = row["xflock_dst_token"]

            xt = (flock_a, flock_b)

            if not xt in xflocks:
                xflocks[xt] = 1
            else:
                xflocks[xt] = xflocks[xt] + 1

        return xflocks

koreapp = Sync()
