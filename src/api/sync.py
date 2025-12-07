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

SQL_GET_FLOCKS_WITH_TIME_LEFT = """
SELECT DISTINCT
    network_token
FROM
    networks, accounts
WHERE
    networks.network_owner = accounts.account_id AND
    accounts.account_time_left > EXTRACT(epoch FROM now())
"""

SQL_GET_CATHEDRALS = """
SELECT
    cathedral_ip, cathedral_port
FROM
    cathedrals
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

    def configure(self, args):
        self.counter = 0
        kore.config.workers = 1
        #kore.config.seccomp_tracing = "yes"
        kore.config.pidfile = "/tmp/sync.pid"
        kore.config.tls_dhparam = "/usr/local/share/kore/ffdhe4096.pem"

        self.deployment = os.getenv("SYNC_DEPLOYMENT", "dev")
        kore.config.deployment = self.deployment

        self.shared_path = os.getenv(
            "SYNC_SHARED_PATH", default="shared"
        )

        self.settings_path = f"{self.shared_path}/settings.conf"

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
        self.cfg = ""

    def config(self, line):
        self.cfg += line + "\n"

    def config_write(self):
        try:
            tmppath = f"{self.settings_path}.tmp"

            fd = os.open(
                path=tmppath,
                flags=(
                    os.O_CREAT | os.O_TRUNC | os.O_WRONLY
                ),
                mode=0o444
            )

            with open(fd, "w") as f:
                f.write(self.cfg)

            os.rename(tmppath, self.settings_path)
        except Exception as e:
            kore.log(kore.LOG_NOTICE, f"failed to write settings {e}")

    async def run(self):
        while True:
            try:
                kore.log(kore.LOG_INFO, f"sync {self.counter} started")
                flocks = await kore.dbquery("db", SQL_GET_FLOCKS_WITH_TIME_LEFT)
                self.config_reset()
                self.counter = self.counter + 1
                self.config(f"# settings {self.counter}")
                for flock in flocks:
                    await self.flock_sync(flock)

                cathedrals = await kore.dbquery("db", SQL_GET_CATHEDRALS)
                kore.log(kore.LOG_INFO, f"cathedrals = {cathedrals}")
                for cathedral in cathedrals:
                    ip = cathedral["cathedral_ip"]
                    port = cathedral["cathedral_port"]
                    self.config(f"federate {ip} {port}")

                self.config_write()
                kore.log(kore.LOG_INFO, f"sync {self.counter} completed")
            except Exception as e:
                kore.log(kore.LOG_NOTICE, f"sync failed: {e}")

            await kore.suspend(30 * 1000)

    async def flock_sync(self, flock):
        token = flock["network_token"]
        kore.log(kore.LOG_INFO, f"syncing {flock}")

        devices = await kore.dbquery("db",
            SQL_GET_DEVICES_PER_FLOCK,
            params=[token]
        )

        self.config(f"flock {token} {{")

        path = f"{self.shared_path}/identities"
        os.makedirs(path, exist_ok=True)

        path = f"{self.shared_path}/identities/flock-{token}"
        os.makedirs(path, exist_ok=True)

        for device in devices:
            kek = hex(int(device["device_kek"]))
            pubkey = device["device_pubkey"]
            limit = device["device_bw_limit"]
            cid = device["device_cathedral_id"]
            key = device["device_cathedral_key"]

            path = f"{self.shared_path}/identities/flock-{token}/{cid}.key"
            tmppath = f"{path}.tmp"

            with open(tmppath, "wb") as f:
                f.write(bytes.fromhex(key))

            os.rename(tmppath, path)

            if pubkey != "NO-KEY":
                path = f"{self.shared_path}/identities/flock-{token}/{cid}.pub"
                tmppath = f"{path}.tmp"
                with open(tmppath, "wb") as f:
                    f.write(bytes.fromhex(pubkey))
                os.rename(tmppath, path)

            self.config(f"\tallow {cid} spi {kek} {limit}")

        self.config(f"\tambry /home/cathedral/shared/ambries/ambry-{token}")
        self.config("}")

koreapp = Sync()
