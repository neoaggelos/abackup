#!/usr/bin/python3

import argparse
from collections import defaultdict
from datetime import datetime
import os
import parse
import re
import subprocess
import sys
import tarfile
import time
import yaml


def error(msg):
    print(msg)
    sys.exit(-1)


def timestamp():
    return '{}'.format(int(time.time()))


def _parse(regex, line):
    try:
        return parse.parse(regex, line).named
    except:
        return {}


def s3_format_path(args, path):
    return 's3://{}/{}'.format(args.config.s3bucket, path)


def parse_backup_file(args, line):
    full_re = s3_format_path(args, args.config.full_backup_name)
    diff_re = s3_format_path(args, args.config.diff_backup_name)

    result = _parse(diff_re, line) or _parse(full_re, line)
    for ts in ['diff_ts', 'full_ts']:
        try:
            if ts in result:
                result[ts] = int(result[ts])
        except:
            pass

    if result:
        result['path'] = line

    return result


def s3_get_backups(args):
    path = s3_format_path(args, os.path.dirname(args.config.full_backup_name))
    stdout = subprocess.run(
        ['s3cmd', 'ls', path], stdout=subprocess.PIPE).stdout.decode()
    result = defaultdict(lambda: [])
    for line in stdout.split('\n'):
        parsed = parse_backup_file(args, line.split(' ')[-1])
        if parsed and (not args.id or args.id == 'all' or parsed['id'] == args.id):
            result[parsed['id']].append(parsed)

    return result


def s3_get_latest_full_backup(args, backups):
    res = {'full_ts': -1}

    for backup in backups[args.id]:
        if 'diff_ts' not in backup and backup['full_ts'] > res['full_ts']:
            res = backup

    return res


def s3_get_latest_diff_backup(args, backups, full_ts):
    res = {'diff_ts': -1}

    for backup in backups[args.id]:
        if 'diff_ts' in backup and backup['full_ts'] == full_ts and backup['diff_ts'] > res['diff_ts']:
            res = backup

    return res


def s3_get_file(args, remote_path, dest_path):
    print(f'Retrieving {remote_path}')
    subprocess.run(['s3cmd', 'get', remote_path, dest_path, '--force'])


class Config():
    s3cmd = 's3cmd'
    s3cmd_cfg = os.path.expanduser('~/.s3cfg')
    s3bucket = 'BUCKET'

    full_backup_name = '{id}_full_{full_ts}.tar.gz'
    diff_backup_name = '{id}_full_{full_ts}_diff_{diff_ts}.tar.gz'

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


def unarchive(filename, dest_path):
    """Extract files from @filename to @dest_path"""
    abs_dest_path = os.path.absolute(dest_path)
    with tarfile.open(filename, 'r:gz') as t:
        # https://github.com/neoaggelos/abackup/pull/1
        for member in tar.getmembers():
            member_path = os.path.join(abs_dest_path, member.name)
            if os.path.commonprefix([abs_dest_path, member_path]) != abs_dest_path:
                raise Exception("attempted path traversal in tar file")

        t.extractall(dest_path)


def backup(args):
    """Perform full backup"""

    local_fname = '/tmp/{}.tar.gz'.format(args.id)

    if args.after > 0:
        # differential backups
        s3_fname = s3_format_path(args, args.config.diff_backup_name.format_map(
            {**args.__dict__, 'full_ts': args.after, 'diff_ts': timestamp()}))
    else:
        s3_fname = s3_format_path(args, args.config.full_backup_name.format_map(
            {**args.__dict__, 'full_ts': timestamp()}))

    print('[INF] Creating {}'.format(local_fname))
    archive(local_fname, args.dir, args.after)

    if args.s3:
        subprocess.run([args.config.s3cmd, '-c', args.config.s3cmd_cfg, 'put', local_fname, s3_fname])


def list_backups(args):
    backups = s3_get_backups(args)
    for key in s3_get_backups(args):
        print('\n-- {}'.format(key))
        for val in backups[key]:
            print('[{}] [{}] {}'.format('diff' if 'diff_ts' in val else 'full', datetime.fromtimestamp(val.get('diff_ts', val['full_ts'])), val['path']))


def restore(args):
    if not args.id:
        error('[ERR] Missing required parameter --id')

    if not args.dir:
        error('[ERR] Missing required parameter --dir')

    backups = s3_get_backups(args)

    # get latest full backup
    full_backup = s3_get_latest_full_backup(args, backups)
    diff_backup = s3_get_latest_diff_backup(args, backups, full_backup['full_ts'])

    if full_backup['full_ts'] == -1:
        error('[ERR] No backups for {}!'.format(args.id))

    print('Attempting to restore the following backup:\n')
    to_restore = [full_backup['path']]
    if diff_backup['diff_ts'] == -1:
        print('Backup:'.ljust(10), full_backup['path'].ljust(100), datetime.fromtimestamp(full_backup['full_ts']))
    else:
        to_restore.append(diff_backup['path'])
        print('Backup:'.ljust(10), diff_backup['path'].ljust(100), datetime.fromtimestamp(diff_backup['diff_ts']))
        print('Using:'.ljust(10), full_backup['path'].ljust(100), datetime.fromtimestamp(diff_backup['full_ts']))

    print('Backup will be restored under: ', args.dir)

    if not args.force:
        resp = input('\nAre you sure? [y/N] ')
        if resp != 'y':
            error('[ERR] Aborted!')

    for remote_file in to_restore:
        fname = os.path.join('/tmp', os.path.basename(remote_file))
        s3_get_file(args, remote_file, fname)
        unarchive(fname, args.dir)


def abackup(args):
    """Loads configuration and passed control performs the requested action"""

    if args.action == 'backup':
        if not args.id:
            error('[ERR] Missing required parameter --id')

        if not args.dir:
            error('[ERR] Missing required parameter --dir')

        try:
            args.after = s3_get_latest_full_backup(args)['full_ts'] if args.after == 's3' else int(args.after)
        except Exception as e:
            args.after = -1

        return backup(args)

    if args.action == 'list':
        return list_backups(args)

    if args.action == 'restore':
        if args.dir is None:
            args.dir = '/'
        return restore(args)


def main():
    """Parses arguments"""
    parser = argparse.ArgumentParser(description='Backup/restore tool')

    parser.add_argument('action', choices=['backup', 'list', 'restore'])
    parser.add_argument('-d', '--dir', help='Directory to backup/restore files from')
    parser.add_argument('-i', '--id', help='Directory to backup/restore files from')
    parser.add_argument('-c', '--config', help='Path to config file', default='abackup.yml')
    parser.add_argument('-s', '--s3', help='Push backup to S3 storage', default=False, action='store_true')
    parser.add_argument('-a', '--after', help='Only backup files after AFTER (UNIX timestamp). Can be "s3", to pull the latest backup from S3')
    parser.add_argument('-f', '--force', help='Force restore', default=False, action='store_true')
    args = parser.parse_args()

    # parse config file
    args.config = Config(args.config)

    # parse directory
    if args.dir:
        args.dir = os.path.abspath(os.path.realpath(args.dir))

    # backup id
    if args.id and ' ' in args.id:
        error('[ERR] id cannot contain spaces')

    abackup(args)


if __name__ == '__main__':
    main()
