#! /usr/bin/env python3

from os import environ, listdir
from os import system as run_command
from os.path import join as path_join
from os.path import isabs as is_absolute_path
from shutil import move as move_file
from syslog import syslog, LOG_INFO
from pathlib import Path


def get_env(key):
    return environ.get('PFDNLD_' + key)


SYSLOG = True if get_env('NO_SYSLOG') is None else False
COLORS = {
    'red': '\033[1;31m',
    'white': '\033[1;37m',
    'gray': '\033[1;30m',
    'yellow': '\033[1;33m',
    'reset': '\033[0m'
}
EMPTY_COLORS = {item[0]: '' for item in COLORS.items()}
if get_env('NO_COLORIZE') is not None:
    COLORS = EMPTY_COLORS


def log(text, parameters=None):
    if parameters is None:
        parameters = []
    print(text.format(*parameters, **COLORS))
    SYSLOG and syslog(LOG_INFO, text.format(*parameters, **EMPTY_COLORS))


def is_file_modified(filename, last_modify_time):
    path = Path(filename)
    if not path.exists():
        return None
    if last_modify_time is None:
        return path.stat().st_mtime
    diff = last_modify_time - path.stat().st_mtime
    if diff == 0:
        return False
    return path.stat().st_mtime


def link_number_template(link):
    start = link.find('[[')
    end = link.find(']]')
    if start == -1 or end == -1 or start > end:
        return [link]
    extracted_text = link[start+2:end]
    parts = extracted_text.split('-')

    def log_and_return():
        log(
            '{red}bad number template {reset}{white}{!r}{reset}{red} in link {!r}{reset}',
            [extracted_text, link]
        )
        return [link]

    if len(parts) != 2:
        return log_and_return()
    start, end = parts
    if not start.isdigit() or not end.isdigit():
        return log_and_return()
    digits = len(start)
    start, end = int(start), int(end)
    if start >= end or start == 0:
        return log_and_return()
    template = '{:0' + str(digits) + '}'
    links = []
    for number in range(start, end+1):
        links.append(link.replace('[[' + extracted_text + ']]', template.format(number)))
    return links


def read_links_from_file(filename, prefix_path):
    links = []
    if not Path(filename).exists():
        log('{yellow}could not found link file {!r}{reset}', [filename])
        return links
    try:
        fd = open(filename)
    except Exception as open_error:
        log('{red}could not open link file {!r} for reading: {}', [filename, open_error])
        return links
    for line_number, line in enumerate(fd.read().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(' ')
        part_count = len(parts)
        if part_count == 1:
            link, path = line, prefix_path
        elif part_count == 2:
            link, path = parts
            while path and path[0] == '/':
                path = path[1:]
            path = path_join(prefix_path, path)
        else:
            log('{red}detected line {} with unknown parts: {!r}{reset}', [line_number, line])
            continue
        for templated_link in link_number_template(link):
            links.append((templated_link, path))
    for link, output_dir in links:
        log(
            'detected link {yellow}{!r}{reset} with output directory {white}{!r}{reset}',
            [link, output_dir]
        )
    return links


def truncate_file(filename):
    try:
        fd = open(filename, 'w')
    except Exception as open_error:
        log('{red}could not open file {!r} for truncating: {}', [filename, open_error])
        return False
    fd.close()
    return True


def truncate_link_file(filename):
    log('truncating link file {yellow}{!r}{reset}', [filename])
    return truncate_file(filename)


def truncate_download_result_file(filename):
    log('truncating download result file {yellow}{!r}{reset}', [filename])
    return truncate_file(filename)


def append_download_attempt_to_file(filename, link, output_dir):
    try:
        fd = open(filename, 'a')
    except Exception as open_error:
        log('{red}could not open file {!r} for appending attempt status: {}', [filename, open_error])
        return False
    text = '{} {} '.format(link, output_dir)
    length = len(text) + 5  # (len(str(False)))
    try:
        fd.write((length * '*') + '\n' + text)
    except Exception as write_error:
        log('{red}could not write attempt status to file {!r}: {}', [filename, write_error])
        return False
    fd.close()
    return True


def append_download_result_to_file(filename, download_result):
    try:
        fd = open(filename, 'a')
    except Exception as open_error:
        log('{red}could not open file {!r} for appending: {}', [filename, open_error])
        return False
    try:
        fd.write('{}\n'.format(download_result))
    except Exception as write_error:
        log('{red}could not write download result to file {!r}: {}', [filename, write_error])
        return False
    fd.close()
    return True


def download_links_via_command(command, links, result_filename):
    result = []
    for link, output_dir in links:
        append_download_attempt_to_file(result_filename, link, output_dir)
        download_result = download_link_via_command(command, link)
        move_downloaded_files_to_output_directory(output_dir)
        append_download_result_to_file(result_filename, download_result)
        result.append((link, output_dir, download_result))
    return result


def download_link_via_command(command, link):
    command = command.format(**{'link': link})
    print('-' * 80)
    log('attempt to run command {white}{!r}{reset}', [command])
    status = run_command(command)
    print()
    status is 0 and log('link {white}{!r}{reset} downloaded', [link])
    status is not 0 and log('{red}could not download the link {!r}{reset}', [link])
    print('-' * 80)
    return status is 0


def move_downloaded_files_to_output_directory(output_dir):
    files = listdir()
    files is not [] and log('found {white}{}{reset} file(s) in temporary download folder', [len(files)])
    try:
        makedirs(output_dir)
    except FileExistsError:
        pass
    except Exception as make_dir_error:
        log('{red}could not create output directory {!r}: {}{reset}', [output_dir, make_dir_error])
        return
    for item in files:
        if Path(item).is_file():
            out_address = path_join(output_dir, item)
            Path(out_address).exists() and log(
                'file {white}{}{reset} already exists, we try to replace it', [out_address]
            )
            log(
                'attempt to move file {white}{}{reset} to output directory {white}{}{reset}',
                [item, output_dir]
            )
            try:
                move_file(item, out_address)
            except Exception as move_error:
                print('{red}could not move the file {!r} to {!r}: {}{reset}', [item, output_dir, move_error])


if __name__ == '__main__':
    import argparse
    from argparse import RawTextHelpFormatter
    from time import sleep
    from os import chdir, makedirs

    parser = argparse.ArgumentParser(
        description='Watches a file containing download links and runs a command to download them.\n'
                    'The link file is in form of:\n'
                    '# comment\n'
                    '<DOWNLOAD_LINK>\n'
                    '<DOWNLOAD_LINK> <OUTPUT_DIRECTORY>\n\n'
                    'A DOWNLOAD_LINK is a valid http/https download link.\n'
                    'If the links are similar but with a range of differnt numbers, \n'
                    'You can use a template in form of: \n'
                    'http://domain.tld/foo/bar/baz/filename-[[START_NUMBER-END_NUMBER]].mkv \n'
                    'For example: \n'
                    'http://domain.tld/foo/bar/baz/filename-[[001-117]].mkv \n'
                    'Also the OUTPUT_DIRECTORY is joined with --out-dir.\n'
                    'After downloading and moving each downloaded file to --out-dir, it appends the download result \n'
                    'to --download-result-file',
        formatter_class=RawTextHelpFormatter
    )
    parser.add_argument(
        '--tmp-dir',
        required=True,
        dest='tmp_dir',
        help='temporary directory to save files while we are downloading them'
    )
    parser.add_argument(
        '--out-dir',
        required=True,
        dest='out_dir',
        help='output directory to save files'
    )
    parser.add_argument(
        '-l',
        '--link-file',
        required=True,
        dest='link_file',
        help='A file containing download links'
    )
    parser.add_argument(
        '-r',
        '--download-result-file',
        default=None,
        dest='download_result_file',
        help='Write download result (boolean) for each link in this file'
    )
    parser.add_argument(
        '-p',
        '--check-period',
        default=5,
        type=int,
        dest='check_period',
        help='Checks link file every <CHECK_PERIOD> time'
    )
    DEFAULT_COMMAND = 'aria2c ' \
                      '--allow-overwrite=false ' \
                      '-x 16 ' \
                      '--disk-cache=256M ' \
                      '--auto-file-renaming=false ' \
                      '--file-allocation=trunc ' \
                      '\'{link}\''
    parser.add_argument(
        '-c',
        '--command',
        default=DEFAULT_COMMAND,
        dest='command',
        help='A command to download the file. It will replace {link} by actual link address'
    )
    args = parser.parse_args()
    if not args.download_result_file:
        args.download_result_file = args.link_file + '.result'

    if args.command == DEFAULT_COMMAND:
        print('-' * 80)
        log('check for {white}aria2c{white} command ({white}aria2c --version{reset})')
        if run_command('aria2c --version') is not 0:
            log(
                '{red}could not found aria2c command in the system. \n'
                'Install it and try again. \n'
                'For more info see: {reset}{white}https://aria2.github.io/manual/en/html/aria2c.html{reset}'
            )
            exit(1)
        log('{white}aria2c{reset} command is working')
        print('-' * 80)
    for path, name in [
        (args.tmp_dir, 'tmp-dir'),
        (args.out_dir, 'out-dir'),
        (args.link_file, 'link-file'),
        (args.download_result_file, 'download-result-file')
    ]:
        if not is_absolute_path(path):
            log('{red}--{} ({reset}{white}{!r}{reset}{red}) MUST be absolute path address{reset}', [name, path])
            exit(1)
    try:
        makedirs(args.tmp_dir)
    except FileExistsError:
        pass
    except Exception as make_tmp_dir_error:
        log('{red}could not create temporary directory {!r}: {}{reset}', [args.tmp_dir, make_tmp_dir_error])
    try:
        chdir(args.tmp_dir)
    except Exception as chdir_error:
        log('{red}could not change working directory to temporary directory {!r}: {}', [args.tmp_dir, chdir_error])
        exit(1)


    def main(cmd_args):
        link_filename = cmd_args.link_file
        result_filename = cmd_args.download_result_file
        check_period = cmd_args.check_period
        command = cmd_args.command
        output_dir = cmd_args.out_dir
        print('\n\n\n')
        log(
            'Application is started with the following options: \n'
            '{white}link_filename{reset}={yellow}{!r}{reset} \n'
            '{white}download_result_filename{reset}={yellow}{!r}{reset} \n'
            '{white}check_period{reset}={yellow}{!r}{reset} \n'
            '{white}output_directory{reset}={yellow}{!r}{reset} \n'
            '{white}download_command{reset}={yellow}{!r}{reset}',
            [link_filename, result_filename, check_period, output_dir, command]
        )
        print('\n\n\n')
        last_modified_time = None
        truncated_link_file = False
        while True:
            modified_result = is_file_modified(link_filename, last_modified_time)
            if modified_result is False:
                sleep(check_period)
                continue
            if modified_result is None:
                log('{yellow}could not found link file {!r}{reset}', [link_filename])
                sleep(check_period)
                continue
            last_modified_time = modified_result
            if truncated_link_file:
                # I truncated link file at the end of the loop
                # So probably file's modify time is changed because of me
                truncated_link_file = False
                continue
            links = read_links_from_file(link_filename, output_dir)
            if links:
                truncate_download_result_file(result_filename)
                download_result_list = download_links_via_command(command, links, result_filename)
                success_download_for_all_files = True
                for _, _, download_result in download_result_list:
                    if not download_result:
                        success_download_for_all_files = False
                        break
                if success_download_for_all_files:
                    truncate_link_file(link_filename)
                    truncated_link_file = True

    try:
        main(args)
    except KeyboardInterrupt:
        print()
    exit(0)
