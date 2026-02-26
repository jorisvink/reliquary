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

SQL_GET_CATHEDRALS = """
SELECT
    cathedral_ip, cathedral_port, cathedral_descr
FROM
    cathedrals
ORDER BY
    cathedral_ip
"""

SQL_ACCOUNT_FROM_KEY = """
SELECT
    account_id, account_time_left
FROM
    accounts
WHERE    
    account_key = $1
"""

SQL_ACCOUNT_FROM_TOKEN = """
WITH account_info AS (
    SELECT
        account_id, account_time_left, account_key, account_flocks_max
    FROM
        tokens
    JOIN
        accounts ON accounts.account_id = tokens.token_account
    WHERE
        token_value = $1 and token_web = $2
)

UPDATE
    tokens
SET
    token_expires = (EXTRACT(epoch FROM now()) + 2592000)
FROM
    account_info
WHERE
    token_value = $1
RETURNING
    *
"""

SQL_ACCOUNT_CREATE = """
INSERT INTO
    accounts (account_key)
VALUES
    ($1)
RETURNING
    account_id
"""

SQL_ACCOUNT_DELETE = """
DELETE FROM
    accounts
WHERE
    account_id = $1
"""

SQL_ACCOUNT_TIME_ADD = """
UPDATE
    accounts
SET
    account_time_left = (EXTRACT(EPOCH FROM NOW()) + 2678400)
WHERE
    account_id = $1
"""

SQL_TOKEN_CREATE = """
INSERT INTO tokens
    (token_value, token_account, token_web)
VALUES
    ($1, $2, $3)
"""

SQL_NETWORK_CREATE = """
INSERT INTO networks
    (network_token, network_owner)
VALUES
    ($1, $2)
"""

SQL_NETWORK_DELETE = """
DELETE FROM
    networks
WHERE
    network_token = $1 AND network_owner = $2
IS TRUE RETURNING network_id
"""

SQL_NETWORK_GET = """
SELECT
    network_id, network_token
FROM
    networks
WHERE
    network_token = $1 AND network_owner = $2
"""

SQL_NETWORK_GET_OWNER = """
SELECT
    network_id, network_owner
FROM
    networks
WHERE
    network_token = $1
"""

SQL_NETWORK_GET_UNAUTHED = """
SELECT
    network_id, network_owner, network_token
FROM
    networks
WHERE
    network_token = $1
"""

SQL_NETWORK_LIST = """
SELECT
    network_token
FROM
    networks
JOIN
    accounts ON accounts.account_id = networks.network_owner
WHERE
    network_owner = $1
"""

SQL_NETWORK_AMBRY_UPDATE = """
UPDATE
    networks
SET
    network_ambry_update = EXTRACT(EPOCH FROM NOW())
WHERE
    network_token = $1 and network_owner = $2
"""

SQL_XFLOCK_GET = """
SELECT
    xflock_id
FROM
    xflocks
WHERE
    xflock_src = $1 AND xflock_dst = $2 AND xflock_owner = $3
"""

SQL_XFLOCK_CREATE = """
INSERT INTO xflocks
    (xflock_src, xflock_src_token, xflock_dst, xflock_dst_token, xflock_owner)
VALUES
    ($1, $2, $3, $4, $5)
"""

SQL_XFLOCK_LIST = """
SELECT
    xflock_src_token as flock_a,
    xflock_dst_token as flock_b
FROM
    xflocks
WHERE
    xflock_owner = $1
"""

SQL_XFLOCK_LIST_FOR_FLOCK = """
WITH xfl AS (
    SELECT
        xflock_dst_token as other
    FROM
        xflocks
    WHERE
        xflock_src_token = $1 AND
        xflock_owner = $2
)

SELECT
    xfl.other, network_owner
FROM
    networks
JOIN xfl ON xfl.other = networks.network_token
"""

SQL_XFLOCK_DELETE = """
DELETE FROM
    xflocks
WHERE
    xflock_src_token = $1 AND
    xflock_dst_token = $2 AND
    xflock_owner = $3
"""

SQL_DEVICE_CREATE = """
INSERT INTO devices
    (
        device_kek,
        device_cathedral_id,
        device_network,
        device_cathedral_key,
        device_account,
        device_network_token,
        device_pubkey
    )
VALUES
    ($1, $2, $3, $4, $5, $6, $7)
RETURNING
    device_id
"""

SQL_DEVICE_DELETE = """
DELETE FROM
    devices
WHERE
    device_network_token = $1 AND
    device_cathedral_id = $2 AND
    device_account = $3
IS TRUE RETURNING device_id
"""

SQL_DEVICE_APPROVE = """
UPDATE
    devices
SET
    device_approved = 't', device_kek = $3
WHERE
    device_network_token = $1 AND
    device_cathedral_id = $2 AND
    device_approved = 'f'
RETURNING
    device_kek
"""

SQL_DEVICE_LIST = """
SELECT
    device_kek, device_cathedral_id, device_approved, device_created
FROM
devices
    JOIN networks ON networks.network_id = devices.device_network
WHERE
    network_token = $1 AND network_owner = $2 AND device_account = $2
ORDER BY
    device_approved = 'f' DESC, device_kek ASC
"""

SQL_DEVICE_LIST_ALL_FOR_NETWORK = """
SELECT
    device_kek, device_cathedral_id
FROM
devices
    JOIN networks ON networks.network_id = devices.device_network
WHERE
    network_token = $1
"""

SQL_DEVICE_RENEW = """
UPDATE
    devices
SET
    device_cathedral_key = $1
WHERE
    device_cathedral_id = $2 AND device_account = $3
RETURNING
    device_cathedral_id, device_network_token, device_kek
"""

SQL_DEVICE_PUBKEY = """
UPDATE
    devices
SET
    device_pubkey = $1
WHERE
    device_cathedral_id = $2 AND device_account = $3
RETURNING
    device_cathedral_id
"""

SQL_EXPIRE_TOKENS = """
DELETE FROM
    tokens
WHERE
    token_expires < EXTRACT(epoch FROM now())
"""
