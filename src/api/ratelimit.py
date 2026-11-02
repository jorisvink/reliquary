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
import time

PRUNE_INTERVAL = 60 * 1000

REQUESTS_BURST_LIMIT = 2
REQUESTS_PER_SECOND_LIMIT = 1

class RateLimit:
    def __init__(self, app):
        self.app = app
        self.clients = {}

        kore.task_create(self.prune())

    async def prune(self):
        full = REQUESTS_BURST_LIMIT / REQUESTS_PER_SECOND_LIMIT

        while True:
            await kore.suspend(PRUNE_INTERVAL)

            now = time.monotonic()
            idle = [client for client, (_, last) in self.clients.items()
                if now - last >= full]

            for client in idle:
                del self.clients[client]

    def check(self, client, path):
        now = time.monotonic()
        tokens, last = self.clients.get(client, (REQUESTS_BURST_LIMIT, now))

        tokens = min(REQUESTS_BURST_LIMIT,
            tokens + (now - last) * REQUESTS_PER_SECOND_LIMIT)

        if tokens < 1:
            self.clients[client] = (tokens, now)
            kore.log(kore.LOG_NOTICE, f"{client} hit the rate-limit")
            return False

        self.clients[client] = (tokens - 1, now)
        return True
