# Reliquary

Ansible and shell scripts to manage reliquary.se.

Comes with support or zero warranty, this is released as
open-source so others can build upon it if they want too.

## Building

```
$ make
```

which builds it on host, there is an ubuntu-24.04 to build
specifically for ubuntu 24.04 via podman.

```
$ make ubuntu-24.04
```

You can override the git repo's where sanctum, kore or
syncretism are fetched from.

By default these are fetched from github.

```
$ make \
    KORE_GIT=own.server.example:/kore.git \
    SANCTUM_GIT=own.server.example:/sanctum.git \
    SYNCRETISM_GIT=own.server.example:/syncretism.git
```

## Deploying / updating

See docs/deployment.md

## Configurations

The configuration directory you point to (see configs/dev above)
should contain the following files:

### api.yaml

```
api:
    hosts:
        vm001:
            ansible_host: 192.168.122.102
            target_arch: x86_64
```

### cathedrals.yaml

```
cathedrals:
    hosts:
        vm001:
            ansible_host: 192.168.122.102
            target_arch: x86_64
```

### settings.yaml

```
---
p2p_sync: true
nat_port: 4501
api_hostname: vessel.reliquary.se
api_initial_cathedral: 127.0.0.1:4500
syncretism_master: 127.0.0.1:8760
api_initial_cathedral: 127.0.0.1:4500
priest_passphrase: $7$CU..../....WQ6mM0fmdBjnLRMdGKdO71$N0W8CS5r059VoraZQOgbPjL5kivFsR9VIwpv9n2qxr1

ssh_keys:
    - ssh-rsa ...
```

## keys.vault

An ansible vault containing two base64 256-bit secrets:

- federation_secret
- syncretism_secret

You can see **configs/dev** its keys.vault contents (password: test).

## Running locally

Requirements:

- podman
- postgresql
- the usual suspects for local dev

Create a pgsql mock database.

```
$ initdb mockdb
```

Then start it.
```
$ pg_ctl -D mockdb -l pgsql.log start
```

Populate it
```
$ psql -d accounts < src/api/schema.sql
```

Now you can start the API.

```
$ env DBHOST=/path/to/postgresql ./release-<arch>/kore src/api/api.py
```

This makes the API listen on 127.0.0.1:8888 on plain http.

```
$ env DBHOST=/path/to/postgresql ./release-<arch>/kore src/api/sync.py
```

This runs the sync service, which synchronizes the database to files
on disk for cathedral configuration. This is written to a directory
name shared.
