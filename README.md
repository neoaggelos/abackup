# abackup

Simple backup + restore tool, supporting differential backups. Written
in python3. Supports storing and pulling backups from S3 storage.


## Requirements

* python3, python3-tarfile
* s3cmd executable


## Configuration

A single config file `abackup.yml` is used. The sample `abackup.yml.sample`
has sane defaults. Editing the configuration file is only mandatory for
using S3 storage.


## Usage

1. Create a full backup of a given directory

```
$ ./abackup.py backup --dir /path/of/directory/to/backup [--s3]
```

2. Perform a differential backup, using `timestamp` as base:

```
$ ./abackup.py backup --dir /path/of/directory/to/backup [--s3] --after [timestamp]
```

3. Perform a differential backup, using most recent S3 backup as base:

```
$ ./abackup.py backup --dir /path/to/dir --s3 --after s3
```

## Notes

TODO


~ Aggelos Kolaitis <neoaggelos@gmail.com>
