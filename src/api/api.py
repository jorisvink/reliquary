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

import os
import re
import kore
import time
import json
import jinja2
import secrets

from queries import *
from ratelimit import RateLimit

ACCOUNT_URLS = [
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

    if not kore.app().ratelimit.check(req.connection.addr, req.path):
        req.response(429, b'')
        return False

@kore.prerequest
async def token_fetch(req):
    if req.path == "/account/login":
        return

    match = re.findall("^/v1/device/([a-f0-9]{16})/create$", req.path)
    if req.path in UNAUTHED_URLS or match:
        return

    if req.path in ACCOUNT_URLS:
        web = 't'
        token = req.populate_cookies()
        token = req.cookie("token")
    else:
        web = 'f'
        token = req.request_header("x-token")

    if token is None:
        if req.path in ACCOUNT_URLS:
            req.response_header("location", "/account/login")
            req.response(301, b'')
        else:
            req.response(403, b'')
        return False

    res = await kore.dbquery("db", SQL_ACCOUNT_FROM_TOKEN, params=[token, web])

    if len(res) != 1:
        if req.path in ACCOUNT_URLS:
            req.response_header("location", "/account/login")
            req.response(301, b'')
        else:
            req.response(403, b'')
        return False

    now = time.time()
    req.expires = int(res[0]["account_time_left"])
    if req.expires < now:
        if req.path not in ACCOUNT_URLS:
            req.response(403, b'account expired')
            return False
        else:
            req.expires = 0
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
        res = await kore.dbquery("db",
            SQL_ACCOUNT_FROM_KEY,
            params=[req.body]
        )

        if len(res) != 1:
            resp = {
                "cathedral": self.cathedral,
                "natport": self.cathedral_nat
            }

            req.response(200, json.dumps(resp).encode())
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
            req.response(200, b'no such flock')
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
        net = await kore.dbquery("db",
            SQL_NETWORK_GET,
            params=[flock, req.account]
        )

        if len(net) != 1:
            req.response(403, b'')
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
        net = await kore.dbquery("db",
            SQL_NETWORK_GET,
            params=[flock, req.account]
        )

        if len(net) != 1:
            req.response(403, b'')
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
        net = await kore.dbquery("db",
            SQL_NETWORK_GET,
            params=[flock, req.account]
        )

        if len(net) != 1:
            req.response(403, b'')
            return

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
            req.response(400, b'no available KEK ids left')
            return

        res = await kore.dbquery("db",
            SQL_DEVICE_APPROVE,
            params=[flock, device, kek_db]
        )

        if len(res) != 1:
            msg = f"{device} not found or already approved"
        else:
            msg = f"{device} approved, please supply it with {flock}/kek-data/kek-0x{kek}"

        req.response(200, msg.encode())

    async def ambry_upload(self, req, flock):
        net = await kore.dbquery("db",
            SQL_NETWORK_GET,
            params=[flock, req.account]
        )

        if len(net) != 1:
            req.response(403, 'bad request')
            return

        src = f"{self.ambry_path}/ambry-{flock}.tmp"

        if len(req.body) != 7542970 and len(req.body) != 3756730:
            req.response(403, 'bad request, invalid length')
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
            "flocks_max": req.account_max_flocks,
            "expires": int(req.expires)
        }))

    async def account_delete(self, req):
        await kore.dbquery("db",
            SQL_ACCOUNT_DELETE,
            params=[req.account]
        )

        await kore.suspend(1100)
        req.response_header("location", "/account/")
        req.response(302, None)

    async def account_add_time(self, req):
        await kore.dbquery("db",
            SQL_ACCOUNT_TIME_ADD,
            params=[req.account]
        )

        await kore.suspend(1100)
        req.response_header("location", "/account/")
        req.response(302, None)

koreapp = Api()
