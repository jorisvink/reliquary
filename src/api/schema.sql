DROP TABLE IF EXISTS devices;
DROP TABLE IF EXISTS networks;
DROP TABLE IF EXISTS tokens;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS cathedrals;

CREATE TABLE accounts (
    account_id serial primary key,
    account_key varchar(64) not null,
    account_flocks_max int not null default 3,
    account_time_left int not null default EXTRACT(EPOCH FROM NOW()) + 86400
);

CREATE TABLE tokens (
    token_id serial primary key,
    token_value varchar(32) not null,
    token_account serial references accounts(account_id) on delete cascade,
    token_expires int not null default EXTRACT(EPOCH FROM NOW()) + 2592000,
    token_web bool not null default false
);

CREATE TABLE networks (
    network_id serial primary key,
    network_token varchar(32) not null unique,
    network_ambry_update int not null default 0,
    network_owner serial references accounts(account_id) on delete cascade
);

CREATE TABLE xflocks (
    xflock_id serial primary key,
    xflock_src serial references networks(network_id) on delete cascade,
    xflock_src_token varchar(64) not null,
    xflock_dst_token varchar(64) not null,
    xflock_dst serial references networks(network_id) on delete cascade,
    xflock_owner serial references accounts(account_id) on delete cascade,
    xflock_ambry_update int not null default 0
);

CREATE TABLE devices (
    device_id serial primary key,
    device_kek int not null,
    device_cathedral_id varchar(8) not null,
    device_cathedral_key varchar(64) not null,
    device_bw_limit int not null default 25,
    device_pubkey varchar(64) not null default 'NO-KEY',
    device_network serial references networks(network_id) on delete cascade,
    device_account serial references accounts(account_id) on delete cascade,
    device_network_token varchar(64) not null,
    device_approved boolean not null default 'f',
    device_created int not null default EXTRACT(EPOCH FROM NOW())
);

CREATE TABLE cathedrals (
    cathedral_id serial primary key,
    cathedral_ip varchar(15) not null,
    cathedral_port int not null,
    cathedral_descr varchar(64) not null default ''
);

-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO cathedral;
-- GRANT ALL ON ALL SEQUENCES IN SCHEMA public to api;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO api;
