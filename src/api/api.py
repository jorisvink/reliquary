#
# Copyright (c) 2025-2026 Joris Vink <joris@sanctorum.se>
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

import os
import re
import kore
import time
import json
import jinja2
import secrets

from datetime import datetime

from queries import *
from ratelimit import RateLimit

ACCOUNT_URLS = [
    "/account/",
    "/account/time",
    "/account/delete",
    "/account/logout",
    "/account/flock/create"
]

ACCOUNT_URLS_EXPIRED = [
    "/account/",
    "/account/time",
    "/account/delete",
    "/account/logout"
]

UNAUTHED_URLS = [
    "/v1/init",
    "/v1/register",
    "/v1/device/create"
]

@kore.prerequest
async def ratelimit(req):
    req.account = None
    req.account_max_flocks = None

    match = re.findall("^/account/[x]?flock/.*$", req.path)
    if req.path in ACCOUNT_URLS or match:
        return True

    if not kore.app().ratelimit.check(req.connection.addr, req.path):
        req.response(429, None)
        return False

@kore.prerequest
async def token_fetch(req):
    if req.path == "/account/login":
        return

    match = re.findall("^/v1/device/([a-f0-9]{16})/create$", req.path)
    if req.path in UNAUTHED_URLS or match:
        return

    match = re.findall("^/account/[x]?flock/.*$", req.path)
    if req.path in ACCOUNT_URLS or match:
        is_web = True
    else:
        is_web = False

    if is_web:
        web = 't'
        token = req.populate_cookies()
        token = req.cookie("token")
    else:
        web = 'f'
        token = req.request_header("x-token")

    if token is None:
        if is_web:
            req.response_header("location", "/account/login")
            req.response(302, None)
        else:
            req.response(403, None)
        return False

    res = await kore.dbquery("db", SQL_ACCOUNT_FROM_TOKEN, params=[token, web])

    if len(res) != 1:
        if is_web:
            req.response_header("location", "/account/login")
            req.response(302, None)
        else:
            req.response(403, None)
        return False

    now = time.time()
    req.expires = int(res[0]["account_time_left"])
    if req.expires < now:
        if is_web is False:
            req.response(403, b'account expired')
            return False
        elif req.path not in ACCOUNT_URLS_EXPIRED:
            req.response_header("location", "/account/")
            req.response(302, None)
            return False
    else:
        req.expires = req.expires - now

    req.account = res[0]["account_id"]
    req.account_key = res[0]["account_key"]
    req.account_max_flocks = int(res[0]["account_flocks_max"])

@kore.prerequest
def token_verify(req):
    if req.path == "/account/login":
        return

    match = re.findall("^/v1/device/([a-f0-9]{16})/create$", req.path)
    if req.path in UNAUTHED_URLS or match:
        return

    if not req.account:
        return False

class Api:
    def __init__(self):
        kore.app(self)
        self.loader = jinja2.FileSystemLoader("templates")
        self.templates = jinja2.Environment(loader=self.loader)

    def allow(self, seccomp, name):
        try:
            seccomp.allow(name)
        except Exception as e:
            kore.log(kore.LOG_INFO, f"seccomp: {e}")

    def seccomp(self, seccomp):
        self.allow(seccomp, "renameat")
        self.allow(seccomp, "rename")

    def configure(self, args):
        self.dbhost = os.getenv("DBHOST", default="/var/run/postgresql")
        kore.dbsetup("db", f"host={self.dbhost} dbname=accounts")

        kore.config.workers = 1
        kore.config.seccomp_tracing = "yes"
        kore.config.pidfile = "/tmp/api.pid"
        kore.config.tls_dhparam = "/usr/local/share/kore/ffdhe4096.pem"

        self.ratelimit = RateLimit(self)
        self.domain = os.getenv("API_DOMAIN", default="*")
        self.deployment = os.getenv("API_DEPLOYMENT", default="dev")
        self.cathedral_nat = os.getenv("API_CATHEDRAL_NAT", default="4501")
        self.cathedral = os.getenv("API_CATHEDRAL", default="127.0.0.1:4500")
        self.ambry_path = os.getenv("API_AMBRY_PATH", default="shared/ambries")

        kore.task_create(self.expire_tokens())

        kore.config.http_body_max = 7542971
        kore.config.deployment = self.deployment

        if self.deployment != "dev":
            kore.privsep("keymgr",
                root="/home/keymgr",
                runas="keymgr"
            )

            kore.privsep("worker",
                root="/home/api",
                runas="api",
                skip=["chroot"]
            )

            kore.privsep("acme",
                root="/home/acme",
                runas="acme",
                skip=["chroot"]
            )

            kore.server(ip="0.0.0.0", port="443", tls=True)
            d = kore.domain(self.domain, acme=True)
        else:
            kore.server(ip="127.0.0.1", port="8888", tls=False)
            d = kore.domain("*")

        d.route("/account/", self.account, methods=["get", "post" ])
        d.route("/account/time", self.account_add_time, methods=["post"])
        d.route("/account/delete", self.account_delete, methods=["post"])
        d.route("/account/logout", self.account_logout, methods=["post"])

        d.route("/account/flock/create",
            self.account_flock_create, methods=["post"])
        d.route("^/account/flock/([a-f0-9]{16})$",
            self.account_flock_manage, methods=["get"])
        d.route("^/account/flock/([a-f0-9]{16})/delete$",
            self.account_flock_delete, methods=["post"])
        d.route("^/account/flock/([a-f0-9]{16})/([a-f0-9]{8})/approve$",
           self.account_flock_device_approve, methods=["post"])

        d.route("^/account/flock/([a-f0-9]{16})/([a-f0-9]{8})/delete$",
            self.account_flock_device_delete, methods=["post"])
        d.route("^/account/xflock/([a-f0-9]{16})/([a-f0-9]{16})/delete$",
            self.account_xflock_delete, methods=["post"])

        d.route("/account/login", self.account_login, methods=["get", "post"],
            post={
                "account": "^[0-9a-f]{64}$"
            }
        )

        d.route("/v1/cathedrals", self.cathedral_list, methods=["get"])
        d.route("/v1/flock/list", self.flock_list, methods=["get"])
        d.route("/v1/flock/create", self.flock_create, methods=["post"])

        d.route("^/v1/flock/([a-f0-9]{16})/delete$",
            self.flock_delete, methods=["post"])
        d.route("^/v1/device/([a-f0-9]{16})/create$",
            self.device_create, methods=["post"])
        d.route("^/v1/device/([a-f0-9]{16})/([a-f0-9]{8})/delete$",
            self.device_delete, methods=["post"])
        d.route("^/v1/device/([a-f0-9]{16})/([a-f0-9]{8})/approve$",
            self.device_approve, methods=["post"])
        d.route("^/v1/device/list/([a-f0-9]{16})$",
            self.device_list, methods=["get"])

        d.route("/v1/xflock/list", self.xflock_list, methods=["get"])
        d.route("^/v1/xflock/([a-f0-9]{16})/([a-f0-9]{16})/create",
            self.xflock_create, methods=["post"])
        d.route("^/v1/xflock/([a-f0-9]{16})/([a-f0-9]{16})/delete$",
            self.xflock_delete, methods=["post"])
        d.route("^/v1/xflock/([a-f0-9]{16})/([a-f0-9]{16})/ambry$",
            self.xflock_ambry_upload, methods=["post"],
        )

        d.route("/v1/init", self.init, methods=["post"])
        d.route("/v1/register", self.register, methods=["post"])

        d.route("^/v1/ambry/([a-f0-9]{16})$",
            self.ambry_upload, methods=["post"],
        )

    async def expire_tokens(self):
        while True:
            await kore.suspend(30000)
            kore.log(kore.LOG_INFO, "expiring tokens")
            await kore.dbquery("db", SQL_EXPIRE_TOKENS)

    async def cathedral_list(self, req):
        cathedrals = await kore.dbquery("db", SQL_GET_CATHEDRALS)

        resp = ""
        for cathedral in cathedrals:
            ip = cathedral["cathedral_ip"]
            port = cathedral["cathedral_port"]
            descr = cathedral["cathedral_descr"]

            if descr != "":
                resp = resp + f"{descr} - {ip}:{port}\n"
            else:
                resp = resp + f"{ip}:{port}\n"

        req.response(200, resp)

    async def flocks_for_account(self, account):
        res = await kore.dbquery("db",
            SQL_NETWORK_LIST,
            params=[account]
        )

        flocks = []

        if len(res) == 0:
            return flocks

        for flock in res:
            f = {
                "id": flock["network_token"],
            }

            flocks.append(f)

        return flocks

    async def flock_exists_for_account(self, req, flock, web=False):
        net = await kore.dbquery("db",
            SQL_NETWORK_GET,
            params=[flock, req.account]
        )

        if len(net) != 1:
            if web:
                req.response_header("location", "/account/")
                req.response(302, None)
            else:
                req.response(403, None)
            return None

        return net

    async def device_approve_get_kek(self, req, flock, device):
        devices = await kore.dbquery("db",
            SQL_DEVICE_LIST_ALL_FOR_NETWORK,
            params=[flock]
        )

        keks = [True] * 256
        keks[0] = False

        for d in devices:
            kek = int(d["device_kek"])
            keks[kek] = False

        kek = None
        for idx, available in enumerate(keks):
            if available:
                kek_db = f"{idx}"
                kek = f"{idx:02x}"
                break

        if kek is None:
            msg = "No available KEKs left in flock"
            return (False, msg)

        res = await kore.dbquery("db",
            SQL_DEVICE_APPROVE,
            params=[flock, device, kek_db]
        )

        if len(res) != 1:
            msg = f"{device} not found or already approved"
        else:
            msg = f"{device} approved, please supply it with {flock}/kek-data/kek-0x{kek}"

        return (True, msg)

    async def register(self, req):
        account = secrets.token_hex(32)

        res = await kore.dbquery("db",
            SQL_ACCOUNT_CREATE,
            params=[account]
        )

        if len(res) != 1:
            req.response(500, b'internal error')
            return

        token = secrets.token_hex(16)
        account_id = res[0]["account_id"]

        await kore.dbquery("db",
            SQL_TOKEN_CREATE,
            params=[token, account_id, 'f']
        )

        resp = {
            "token": token,
            "account": account,
            "share_id": int(account_id),
            "cathedral": self.cathedral,
            "natport": self.cathedral_nat
        }

        req.response(200, json.dumps(resp).encode())

    async def init(self, req):
        if len(req.body) != 0 and len(req.body) != 64:
            req.response(400, None)
            return

        if len(req.body) == 0:
            resp = {
                "cathedral": self.cathedral,
                "natport": self.cathedral_nat
            }

            req.response(200, json.dumps(resp).encode())
            return

        res = await kore.dbquery("db",
            SQL_ACCOUNT_FROM_KEY,
            params=[req.body]
        )

        if len(res) != 1:
            req.response(403, None)
            return

        account = res[0]["account_id"]
        token = secrets.token_hex(16)

        await kore.dbquery("db",
            SQL_TOKEN_CREATE,
            params=[token, account, 'f']
        )

        resp = {
            "token": token,
            "share_id": int(account),
            "cathedral": self.cathedral,
            "natport": self.cathedral_nat
        }

        req.response(200, json.dumps(resp).encode())

    async def flock_create(self, req):
        flocks = await self.flocks_for_account(req.account)
        if len(flocks) >= req.account_max_flocks:
            req.response(200, b'reached max flocks per account')
            return

        net = secrets.token_hex(7) + "00"

        await kore.dbquery("db",
            SQL_NETWORK_CREATE,
            params=[net, req.account]
        )

        req.response(200, net.encode())

    async def flock_list(self, req):
        flocks = await self.flocks_for_account(req.account)

        resp = {
            "flocks": flocks
        }

        req.response(200, json.dumps(resp).encode())

    async def flock_delete(self, req, network):
        res = await kore.dbquery("db",
            SQL_NETWORK_DELETE,
            params=[network, req.account]
        )

        if len(res) != 1:
            req.response(403, None)
        else:
            req.response(200, b'deleted')

    async def device_create(self, req, flock):
        if len(req.body) != 32:
            req.response(400, b'invalid cosk')
            return

        net = await kore.dbquery("db",
            SQL_NETWORK_GET_UNAUTHED,
            params=[flock]
        )

        if len(net) != 1:
            resp = {
                "cathedral_id": secrets.token_hex(4),
                "cathedral_secret": secrets.token_hex(32),
                "flock": flock
            }

            req.response(200, json.dumps(resp).encode())
            return

        netid = net[0]["network_id"]
        owner = net[0]["network_owner"]
        key = secrets.token_hex(32)
        device = secrets.token_hex(4)

        resp = await kore.dbquery("db",
            SQL_DEVICE_CREATE,
            params=["0", device, netid, key, owner, flock, req.body.hex()]
        )

        resp = {
            "cathedral_id": device,
            "cathedral_secret": key,
            "flock": net[0]["network_token"]
        }

        req.response(200, json.dumps(resp).encode())

    async def device_list(self, req, flock):
        if await self.flock_exists_for_account(req, flock) is None:
            return

        res = await kore.dbquery("db",
            SQL_DEVICE_LIST,
            params=[flock, req.account]
        )

        if len(res) == 0:
            req.response(200, json.dumps({"error": "no devices"}))
            return

        resp = {
            "devices": res
        }

        req.response(200, json.dumps(resp).encode())

    async def device_delete(self, req, flock, device):
        if await self.flock_exists_for_account(req, flock) is None:
            return

        res = await kore.dbquery("db",
            SQL_DEVICE_DELETE,
            params=[flock, device, req.account]
        )

        if len(res) != 1:
            msg = f"{device} does not exist"
        else:
            msg = f"{device} deleted"

        req.response(200, msg.encode())

    async def device_approve(self, req, flock, device):
        result, msg = await self.device_approve_get_kek(req, flock, device)

        if result is False:
            req.response(400, msg.encode())
            return

        req.response(200, msg.encode())

    async def ambry_upload(self, req, flock):
        if await self.flock_exists_for_account(req, flock) is None:
            return

        src = f"{self.ambry_path}/ambry-{flock}.tmp"

        if len(req.body) != 7542970 and len(req.body) != 3756730:
            req.response(403, None)
            return

        with open(src, "wb") as f:
            f.write(req.body)

        dst = f"{self.ambry_path}/ambry-{flock}"
        os.rename(src, dst)

        await kore.dbquery("db",
            SQL_NETWORK_AMBRY_UPDATE,
            params=[flock, req.account]
        )

        req.response(200, b'ambry uploaded')

    async def account_logout(self, req):
        cookie = "token=delete;HttpOnly;Path=/account/;Expires=Thu, 01 Jan 1970 00:00:00 GMT"
        req.response_header("set-cookie", cookie)
        req.response_header("location", "/account/login")
        req.response(302, None)

    async def account_login(self, req):
        if req.method == kore.HTTP_METHOD_POST:
            req.populate_post()
            account = req.argument("account")

            if account is None:
                req.response(400, b'bad request')
                return

            res = await kore.dbquery("db",
                SQL_ACCOUNT_FROM_KEY,
                params=[account]
            )

            if len(res) != 1:
                req.response_header("location", "/account/login")
                req.response(302, None)
                return

            account = res[0]["account_id"]
            token = secrets.token_hex(16)

            await kore.dbquery("db",
                SQL_TOKEN_CREATE,
                params=[token, account, 't']
            )

            if self.deployment != "dev":
                cookie = f"token={token};HttpOnly;Secure;Path=/account/"
            else:
                cookie = f"token={token};HttpOnly;Path=/account/"

            req.response_header("set-cookie", cookie)
            req.response_header("location", "/account/")
            req.response(302, None)
        else:
            tmpl = self.templates.get_template("login.html")
            req.response_header("content-type", "text/html; charset=utf-8")
            req.response(200, tmpl.stream())

    async def account(self, req):
        flocks = await self.flocks_for_account(req.account)
        tmpl = self.templates.get_template("account.html")
        req.response_header("content-type", "text/html; charset=utf-8")
        req.response(200, tmpl.stream({
            "id": req.account,
            "flocks": flocks,
            "account": req.account_key,
            "flocks_cur": len(flocks),
            "flocks_max": req.account_max_flocks,
            "expires": int(req.expires)
        }))

    async def account_delete(self, req):
        await kore.dbquery("db",
            SQL_ACCOUNT_DELETE,
            params=[req.account]
        )

        req.response_header("location", "/account/")
        req.response(302, None)

    async def account_add_time(self, req):
        await kore.dbquery("db",
            SQL_ACCOUNT_TIME_ADD,
            params=[req.account]
        )

        req.response_header("location", "/account/")
        req.response(302, None)

    async def account_flock_create(self, req):
        flocks = await self.flocks_for_account(req.account)
        if len(flocks) < req.account_max_flocks:
            net = secrets.token_hex(7) + "00"

            await kore.dbquery("db",
                SQL_NETWORK_CREATE,
                params=[net, req.account]
            )

        req.response_header("location", "/account/")
        req.response(302, None)

    async def account_flock_delete(self, req, flock):
        res = await kore.dbquery("db",
            SQL_NETWORK_DELETE,
            params=[flock, req.account]
        )

        req.response_header("location", "/account/")
        req.response(302, None)

    async def account_flock_manage(self, req, flock):
        if await self.flock_exists_for_account(req, flock, web=True) is None:
            return

        xfl = await kore.dbquery("db",
            SQL_XFLOCK_LIST_FOR_FLOCK,
            params=[flock, req.account]
        )

        devices = await kore.dbquery("db",
            SQL_DEVICE_LIST,
            params=[flock, req.account]
        )

        for device in devices:
            kek = int(device["device_kek"])
            ts = int(device["device_created"])
            date = datetime.utcfromtimestamp(ts)
            device["kek_id"] = f"{kek:02x}"
            device["created"] = date.strftime("%Y-%m-%d %H:%M:%S")

        tmpl = self.templates.get_template("flock.html")
        req.response_header("content-type", "text/html; charset=utf-8")
        req.response(200, tmpl.stream({
            "id": req.account,
            "flock": flock,
            "xflocks": xfl,
            "devices": devices,
        }))

    async def account_flock_device_approve(self, req, flock, device):
        if await self.flock_exists_for_account(req, flock, web=True) is None:
            return

        result, msg = await self.device_approve_get_kek(req, flock, device)

        req.response_header("location", f"/account/flock/{flock}")
        req.response(302, None)

    async def account_flock_device_delete(self, req, flock, device):
        if await self.flock_exists_for_account(req, flock, web=True) is None:
            return

        res = await kore.dbquery("db",
            SQL_DEVICE_DELETE,
            params=[flock, device, req.account]
        )

        req.response_header("location", f"/account/flock/{flock}")
        req.response(302, None)

    async def account_xflock_delete(self, req, flock_a, flock_b):
        src = await self.flock_exists_for_account(req, flock_a)
        if src is None:
            return

        await kore.dbquery("db",
            SQL_XFLOCK_DELETE,
            params=[flock_a, flock_b, req.account]
        )

        req.response_header("location", f"/account/flock/{flock_a}")
        req.response(302, None)

    async def xflock_list(self, req):
        xfl = await kore.dbquery("db",
            SQL_XFLOCK_LIST,
            params=[req.account]
        )

        resp = {
            "xflocks": xfl
        }

        req.response(200, json.dumps(resp).encode())

    async def xflock_create(self, req, flock_a, flock_b):
        src = await self.flock_exists_for_account(req, flock_a)
        if src is None:
            return

        dst = await kore.dbquery("db",
            SQL_NETWORK_GET_OWNER,
            params=[flock_b]
        )

        if len(dst) != 1:
            req.response(403, None)
            return

        src_id = src[0]["network_id"]
        dst_id = dst[0]["network_id"]
        dst_owner = dst[0]["network_owner"]

        xfl = await kore.dbquery("db",
            SQL_XFLOCK_GET,
            params=[src_id, dst_id, req.account]
        )

        if len(xfl) != 0:
            xfl = await kore.dbquery("db",
                SQL_XFLOCK_GET,
                params=[dst_id, src_id, dst_owner]
            )

            if len(xfl) == 1:
                resp = "The xflock is already established"
            else:
                resp = "Ask the other party to run:\n" \
                      f"    $ reliquary-xflock-create {flock_b} {flock_a}"

            req.response(200, resp.encode())
            return

        await kore.dbquery("db",
            SQL_XFLOCK_CREATE,
            params=[src_id, flock_a, dst_id, flock_b, req.account]
        )

        xfl = await kore.dbquery("db",
            SQL_XFLOCK_GET,
            params=[dst_id, src_id, dst_owner]
        )

        if len(xfl) == 0:
            resp = "Ask the other party to run:\n" \
                  f"    $ reliquary-xflock-create {flock_b} {flock_a}"
        else:
            resp = "The xflock has been established"

        req.response(200, resp.encode())

    async def xflock_delete(self, req, flock_a, flock_b):
        src = await self.flock_exists_for_account(req, flock_a)
        if src is None:
            return

        await kore.dbquery("db",
            SQL_XFLOCK_DELETE,
            params=[flock_a, flock_b, req.account]
        )

        req.response(200, b"The xflock binding has been removed")

    async def xflock_ambry_upload(self, req, flock_a, flock_b):
        if len(req.body) != 7542970:
            req.response(403, None)
            return

        src = await self.flock_exists_for_account(req, flock_a)
        if src is None:
            return

        dst = await kore.dbquery("db",
            SQL_NETWORK_GET_OWNER,
            params=[flock_b]
        )

        if len(dst) != 1:
            req.response(403, None)
            return

        src_id = src[0]["network_id"]
        dst_id = dst[0]["network_id"]
        dst_owner = dst[0]["network_owner"]

        xfl = await kore.dbquery("db",
            SQL_XFLOCK_GET,
            params=[src_id, dst_id, req.account]
        )

        if len(xfl) != 1:
            req.response(403, None)
            return

        xfl = await kore.dbquery("db",
            SQL_XFLOCK_GET,
            params=[dst_id, src_id, dst_owner]
        )

        if len(xfl) != 1:
            req.response(403, None)
            return

        a_id = int(flock_a, 16)
        b_id = int(flock_b, 16)

        if b_id < a_id:
            tmp = flock_a
            flock_a = flock_b
            flock_b = tmp

        src = f"{self.ambry_path}/ambry-{flock_a}_{flock_b}.tmp"

        with open(src, "wb") as f:
            f.write(req.body)

        dst = f"{self.ambry_path}/ambry-{flock_a}_{flock_b}"
        os.rename(src, dst)

        req.response(200, b'ambry uploaded')

koreapp = Api()
