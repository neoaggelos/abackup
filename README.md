# abackup

Simple backup + restore tool, supporting differential backups. Written
in python3. Supports storing and pulling backups from S3 storage.


## Requirements

* Python 3
* tar executable with ability to compress/uncompress `.tar.gz` files
* s3cmd executable


## Configuration

A single config file `abackup.yml` is used. The sample `abackup.yml.sample`
has sane defaults. Editing the configuration file is only mandatory for
using S3 storage.


## Usage

1. Create a full backup of a given directory

```
$ ./abackup.py full-backup --dir /path/of/directory/to/backup
```


## Notes
