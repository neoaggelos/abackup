#!/usr/bin/python3

import argparse
import os
import re
import subprocess
import tarfile
import time
import yaml


def timestamp():
    return '{}'.format(int(time.time()))


def s3_get_latest_full_backup_time(args):
    path = 's3://{}/{}/'.format(args.config.s3bucket, os.path.dirname(args.config.full_backup_name))
    stdout = subprocess.run(['s3cmd', 'ls', path], stdout=subprocess.PIPE).stdout.decode()
    result = []
    for line in stdout.split('\n'):
        match = re.match(r'.*s3:\/\/{}\/backups\/{}_full_(\d+)\.tar\.gz'.format(args.config.s3bucket, args.id), line)
        if match and match.groups():
            result.append(int(match.groups()[0]))

    return max(result)

class Config():
    s3cmd = 's3cmd'
    s3cmd_cfg = os.path.expanduser('~/.s3cfg')
    s3bucket = 'evocdn'

    full_backup_name = 'backups/{id}_full_{full_date}.tar.gz'
    diff_backup_name = 'backups/{id}_full_{full_date}_diff_{diff_date}.tar.gz'

    overrides = {}

    def __init__(self, fname=None):
        try:
            with open(fname, 'r') as fin:
                contents = yaml.safe_load(fin.read())

            for k, v in contents.items():
                if hasattr(self, k):
                    setattr(self, k, v)

        except:
            pass


def archive(filename, source_path, after=-1):
    """Creates archive @filename with files from source_path, if their
    modification times are greater than @after"""
    with tarfile.open(filename, 'w:gz') as tar:
        for root, _, files in os.walk(source_path):
            for fname in files:
                full_name = os.path.join(root, fname)

                st = os.stat(full_name)
                if st.st_mtime >= after:
                    tar.add(full_name)


def backup(args):
    """Perform full backup"""

    local_fname = '/tmp/{}.tar.gz'.format(args.id)

    if args.after > 0:
        # differential backups
        s3_fname = 's3://{}/{}'.format(args.config.s3bucket, args.config.diff_backup_name.format_map({**args.__dict__, 'full_date': args.after, 'diff_date': timestamp()}))
    else:
        s3_fname = 's3://{}/{}'.format(args.config.s3bucket, args.config.full_backup_name.format_map({**args.__dict__, 'full_date': timestamp()}))

    print('Creating {}'.format(local_fname))
    archive(local_fname, args.dir, args.after)

    if args.s3:
        subprocess.run([args.config.s3cmd, '-c', args.config.s3cmd_cfg, 'put', local_fname, s3_fname])


def abackup(args):
    """Loads configuration and passed control performs the requested action"""

    if args.action == 'backup':
        return backup(args)


def main():
    """Parses arguments"""
    parser = argparse.ArgumentParser(description='Backup/restore tool')

    parser.add_argument('action', choices=['backup', 'restore'])
    parser.add_argument('-d', '--dir', help='Directory to backup/restore files from')
    parser.add_argument('-i', '--id', help='Directory to backup/restore files from')
    parser.add_argument('-c', '--config', help='Path to config file', default='abackup.yml')
    parser.add_argument('-s', '--s3', help='Push backup to S3 storage', default=False, action='store_true')
    parser.add_argument('-a', '--after', help='Only backup files after AFTER (UNIX timestamp). Can be "s3", to pull the latest backup from S3')
    args = parser.parse_args()

    # parse directory
    args.dir = os.path.abspath(os.path.realpath(args.dir))

    # parse config file
    args.config = Config(args.config)

    # backup id
    args.id = (args.id or args.config.overrides.get(args.dir, {}).get('id') or args.dir).replace('/', '_')

    # for differential backups
    try:
        args.after = s3_get_latest_full_backup_time(args) if args.after == 's3' else int(args.after)
    except Exception as e:
        args.after = -1

    abackup(args)


if __name__ == '__main__':
    main()
