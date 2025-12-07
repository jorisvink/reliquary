# Deploying a new reliquary

## Building

Make sure you built all the reliquary required files.

## Initial API Deployment

```
$ env ROOT=1 ./scripts/update-ubuntu.sh \
    /path/to/config --limit api_host
```

```
$ env API_INIT=1 ./scripts/deploy-api.sh \
    /path/to/config --limit api_host
```

## Manual db steps

The ansible scripts aren't perfect and do not apply the required
src/api/schema.sql automatically right now.

In order to do that, do as follows:

```
$ ssh priest@api_host
$ sudo su - postgres
$ psql -d accounts
<copy in contents of schema.sql>
<press enter>
<exit>
```

Now rerun the deploy-api.sh script to fixup the permissions.

```
$ ./scripts/deploy-api.sh /path/to/config --limit api_host
```

And then finally start-up everything

```
$ ./scripts/restart-api.h /path/to/config --limit api_host
```

Luckily the API db should only be a one-time deployment.

## Initial cathedral deployment

Note that if the cathedral is the same as the api you do not
need ROOT=1 and CATHEDRAL_INIT=1.

```
$ env ROOT=1 ./scripts/update-ubuntu.sh \
    /path/to/config --limit cathedral_host
```

```
$ env CATHEDRAL_INIT=1 ./scripts/deploy-cathedral.sh \
    /path/to/config --limit cathedral_host
```

```
$ ./scripts/restart-cathedral.h /path/to/config --limit cathedral_host
```

If the cathedral isn't the api_initial_cathedral you need to
manually add it to the api-db under cathedrals.
