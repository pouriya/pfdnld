#! /usr/bin/env python3

from os import environ, listdir
from os import system as run_command
from os.path import join as path_join
from os.path import isabs as is_absolute_path
from os.path import basename as path_basename
from shutil import move as move_file
from syslog import syslog, LOG_INFO
from pathlib import Path
from json import dumps as json_encode
from json import loads as json_decode
import http.client as http_client
import urllib.parse as url_parser


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
DEFAULT_HTTP_CONNECT_TIMEOUT = 15


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
    try:
        fd = open(filename, 'w')
    except Exception as open_error:
        log('{red}could not open file {yellow}{!r}{reset}{red} for writing: {}', [filename, open_error])
        return False
    try:
        fd.write('{}\n'.format(json_encode([])))
    except Exception as write_error:
        log('{red}could not write empty download result to file {yellow}{!r}{reset}{red}: {}', [filename, write_error])
        return False
    fd.close()
    return True


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


def append_download_result_to_file(filename, link, output_directory, download_result=None):
    try:
        fd = open(filename)
    except Exception as open_error:
        log('{red}could not open file {yellow}{!r}{reset}{red} for reading: {}', [filename, open_error])
        return False
    try:
        data = fd.read()
    except Exception as open_error:
        log('{red}could not read file {yellow}{!r}{reset}{red}: {}', [filename, open_error])
        return False
    fd.close()
    try:
        data = json_decode(data)
        data_type = type(data)
        if data_type != list:
            raise ValueError("Excepted list, got {!r}".format(data_type))
    except Exception as decode_error:
        log('{red}could not decode file {yellow}{!r}{reset}{red} data: {}', [filename, decode_error])
        return False
    if download_result is None:
        data.append({'link': link, 'output_directory': output_directory, 'status': 'waiting'})
    else:
        for item in data:
            if item['link'] == link:
                if download_result:
                    item['status'] = 'downloaded'
                else:
                    item['status'] = 'error'
    try:
        fd = open(filename, 'w')
    except Exception as open_error:
        log('{red}could not open file {yellow}{!r}{reset}{red} for writing: {}', [filename, open_error])
        return False
    try:
        fd.write('{}\n'.format(json_encode(data, indent=4)))
    except Exception as write_error:
        log('{red}could not write download result to file {yellow}{!r}{reset}{red}: {}', [filename, write_error])
        return False
    fd.close()
    return True


def download_links_via_command(
    command,
    links,
    host,
    application_token,
    client_token,
    priority,
    title,
    tls,
    markdown,
    port,
    http_connection_timeout
):
    result = []
    for link, output_dir in links:
        extras = None
        before_download_text = 'Downloading {} to {}'
        after_download_text = ' {} to {}'
        if markdown:
            extras = {'client::display': {'contentType': 'text/markdown'}}
            before_download_text = 'Downloading \n**{}** \nto \n**{}**'
            after_download_text = ' \n**{}** \nto \n**{}**'
        filename = path_basename(url_parser.urlparse(link).path)
        send_notification_result = send_notification(
            host,
            before_download_text.format(filename, output_dir),
            application_token,
            priority,
            title,
            tls,
            extras,
            port,
            http_connection_timeout
        )
        download_result = download_link_via_command(command, link)
        move_downloaded_files_to_output_directory(output_dir)
        if send_notification_result is not False:
            delete_notification(
                host,
                send_notification_result,
                client_token,
                tls,
                port,
                http_connection_timeout
            )
        message_prefix = 'Downloaded' if download_result else 'Error downloading'
        send_notification(
            host,
            message_prefix + after_download_text.format(filename, output_dir),
            application_token,
            priority,
            title,
            tls,
            extras,
            port,
            http_connection_timeout
        )
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


def make_http_connection(host, port, tls, timeout):
    default_port = 443 if tls else 80
    port = port if port is not None else default_port
    timeout = timeout if timeout is not None else DEFAULT_HTTP_CONNECT_TIMEOUT
    try:
        if tls:
            http_connection = http_client.HTTPSConnection(host, port=port, timeout=timeout)
        else:
            http_connection = http_client.HTTPConnection(host, port=port, timeout=timeout)
    except Exception as connect_error:
        log(
            '{red}could not connect to {reset}{yellow}{}:{}{reset}{red}:{reset} {white}{}{reset}',
            [host, port, connect_error]
        )
        return False
    return http_connection


def read_and_decode_http_response(http_connection, host, port, http_path, body, log_text):
    try:
        http_response = http_connection.getresponse()
    except Exception as request_error:
        log(
            '{red}could not get response from {reset}{yellow}{}:{}/{}{reset}{red} with body{reset} {yellow}{}{reset}{re'
            'd}:{reset} {white}{}{reset}',
            [host, port, http_path, body, request_error]
        )
        return False
    try:
        response = http_response.read()
    except Exception as response_error:
        log(
            '{red}could not read response from {reset}{yellow}{}:{}/{}{reset}{red} with body{reset} {yellow}{}{reset}{r'
            'ed}:{reset} {white}{}{reset}',
            [host, port, http_path, body, response_error]
        )
        return False
    if not response:
        return None
    try:
        response = json_decode(response)
    except Exception as decode_error:
        log(
            '{red}could not decode response {reset}{yellow}{!r}{reset}{red} from {reset}{yellow}{}:{}/{}{reset}{red} wi'
            'th body{reset} {yellow}{}{reset}{red}:{reset} {white}{}{reset}',
            [response, host, port, http_path, body, decode_error]
        )
        return False
    if 'errorDescription' in response.keys():
        reason = response['errorDescription']
        log(
            '{red}could {} {reset}{yellow}{}:{}/{}{reset}{red} with body{reset} {yellow}{}{reset}{red'
            '}:{reset} {white}{}{reset}',
            [log_text, host, port, http_path, body, reason]
        )
        return False
    return response


def send_notification(
        host,
        message,
        application_token,
        priority=None,
        title=None,
        tls=True,
        extras=None,
        port=None,
        timeout=None
):
    http_connection = make_http_connection(host, port, tls, timeout)
    if http_connection is False:
        return False
    http_path = '/message?' + url_parser.urlencode({'token': application_token})
    log_http_path = '/message?token=' + \
                    application_token[0] + ((len(application_token) - 2) * '*') + application_token[-1]
    http_headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    priority = priority if priority is not None else 0
    body = {'message': message, 'priority': priority}
    if title:
        body['title'] = title
    if extras:
        body['extras'] = extras
    body_json = json_encode(body, sort_keys=True)
    try:
        http_connection.request('POST', http_path, body_json, http_headers)
    except Exception as request_error:
        log(
            '{red}could not send request to {reset}{yellow}{}:{}/{}{reset}{red} with body{reset} {yellow}{}{reset}{red}'
            ':{reset} {white}{}{reset}',
            [host, port, log_http_path, body_json, request_error]
        )
        return False
    response = read_and_decode_http_response(
        http_connection,
        host,
        port,
        log_http_path,
        body_json,
        'send notification to'
    )
    if type(response) is dict:
        log(
            '{white}sent notification to {reset}{yellow}{}:{}{reset}{red} with body{reset} {yellow}{}{reset}',
            [host, port, body_json]
        )
        return response['id']
    return response


def delete_notification(
    host,
    message_id,
    client_token,
    tls=True,
    port=None,
    timeout=None
):
    http_connection = make_http_connection(host, port, tls, timeout)
    if http_connection is False:
        return False
    http_path = '/message/{}'.format(message_id)
    http_headers = {'Accept': 'application/json', 'Content-Type': 'application/json', 'X-Gotify-Key': client_token}
    try:
        http_connection.request('DELETE', http_path, '', http_headers)
    except Exception as request_error:
        log(
            '{red}could not send request to {reset}{yellow}{}:{}{}{reset}{red}:{reset} {white}{}{reset}',
            [host, port, http_path, request_error]
        )
        return False
    response = read_and_decode_http_response(http_connection, host, port, http_path, '', 'delete notification from')
    if response is None:
        log(
            '{red}deleted notification from {reset}{yellow}{}:{}{}{reset}',
            [host, port, http_path]
        )
        return True
    return response


def fetch_link_list(
        host,
        client_token,
        application_id,
        prefix_path,
        last_message_id=0,
        tls=True,
        port=None,
        timeout=None,
        limit=100
):
    http_headers = {'Accept': 'application/json', 'Content-Type': 'application/json', 'X-Gotify-Key': client_token}
    notification_list = []
    since_message_id = 0
    while True:
        http_connection = make_http_connection(host, port, tls, timeout)
        if http_connection is False:
            break
        http_path = '/application/{}/message?'.format(application_id) + \
                    url_parser.urlencode({'since': since_message_id, 'limit': limit})
        try:
            http_connection.request('GET', http_path, '', http_headers)
        except Exception as request_error:
            log(
                '{red}could not send request to {reset}{yellow}{}:{}/{}:{reset} {white}{}{reset}',
                [host, port, http_path, request_error]
            )
            break
        response = read_and_decode_http_response(
            http_connection,
            host,
            port,
            http_path,
            '',
            'fetch notification(s) from'
        )
        if type(response) is dict:
            messages = response['messages']
            message_count = len(messages)
            if message_count is 0:
                break
            fetch_last_message_id = int(messages[-1]['id'])
            added_to_notifications = False
            for message in messages:
                if int(message['id']) == last_message_id:
                    break
                notification_list.append(message)
                added_to_notifications = True
            since_message_id = fetch_last_message_id
            added_to_notifications and log(
                '{white}received {reset}{yellow}{}{reset}{white} notification(s) ({yellow}{}{reset}{white}-{reset}{yell'
                'ow}{}{reset}{white}){reset}',
                [message_count, fetch_last_message_id, messages[0]['id']]
            )
            continue
        break
    notification_list.reverse()
    log(
        '{white}received {reset}{yellow}{}{reset}{white} notification(s){reset}',
        [len(notification_list)]
    )
    links = []
    for notification in notification_list:
        message = notification['message'].strip()
        if not message:
            continue
        parts = message.split(' ')
        part_count = len(parts)
        if part_count == 1:
            link, path = message, prefix_path
        elif part_count == 2:
            link, path = parts
            while path and path[0] == '/':
                path = path[1:]
            path = path_join(prefix_path, path)
        else:
            log('{red}detected message with unknown parts: {!r}{reset}', [message])
            continue
        for templated_link in link_number_template(link):
            links.append((templated_link, path))
    if notification_list:
        last_message_id = notification_list[-1]['id']
    return links, last_message_id


if __name__ == '__main__':
    import argparse
    from argparse import RawTextHelpFormatter
    from time import sleep
    from os import chdir, makedirs

    parser = argparse.ArgumentParser(
        description='Watches Gotify for download links and runs a command to download them.\n'
                    'The message should be in form of:\n'
                    '<DOWNLOAD_LINK>\n'
                    'or \n'
                    '<DOWNLOAD_LINK> <OUTPUT_DIRECTORY>\n'
                    'A DOWNLOAD_LINK is a valid http/https download link.\n'
                    'If the links are similar but with a range of differnt numbers, \n'
                    'You can use a template in form of: \n'
                    'http://domain.tld/foo/bar/baz/filename-[[START_NUMBER-END_NUMBER]].mkv \n'
                    'For example: \n'
                    'http://domain.tld/foo/bar/baz/filename-[[001-117]].mkv \n'
                    'Also the OUTPUT_DIRECTORY is joined with --out-dir.\n'
                    'Before/After download and moving each downloaded file to --out-dir, it pushes the download result '
                    'to Gotify',
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
        '-H',
        '--host',
        required=True,
        dest='host',
        help='gotify hostname'
    )
    parser.add_argument(
        '-P',
        '--port',
        default=None,
        dest='port',
        help='gotify port number'
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
    parser.add_argument(
        '--application-token',
        required=True,
        dest='application_token',
        help='gotify application token'
    )
    parser.add_argument(
        '--application-id',
        required=True,
        dest='application_id',
        help='gotify application id'
    )
    parser.add_argument(
        '--client-token',
        required=True,
        dest='client_token',
        help='gotify client token'
    )
    parser.add_argument(
        '--connection-timeout',
        default=15,
        type=int,
        dest='http_connection_timeout',
        help='HTTP connection timeout'
    )
    parser.add_argument(
        '--tls',
        action='store_true',
        default=False,
        dest='tls',
        help='Use TLS (httpS) or not'
    )
    parser.add_argument(
        '--pagination-limit',
        default=10,
        type=int,
        dest='fetch_pagination_limit',
        help='HTTP connection timeout'
    )
    parser.add_argument(
        '--notification-priority',
        default=0,
        type=int,
        dest='priority',
        help='gotify notification priority'
    )
    parser.add_argument(
        '--notification-title',
        default='File Downloader',
        dest='title',
        help='gotify notification title'
    )
    parser.add_argument(
        '--markdown',
        action='store_true',
        default=False,
        dest='markdown',
        help='gotify render message to markdown'
    )
    args = parser.parse_args()

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
        (args.out_dir, 'out-dir')
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
        host = cmd_args.host
        port = cmd_args.port
        application_token = cmd_args.application_token
        application_id = cmd_args.application_id
        client_token = cmd_args.client_token
        http_connection_timeout = cmd_args.http_connection_timeout
        tls = cmd_args.tls
        fetch_pagination_limit = cmd_args.fetch_pagination_limit
        priority = cmd_args.priority
        title = cmd_args.title
        markdown = cmd_args.markdown
        check_period = cmd_args.check_period
        command = cmd_args.command
        output_dir = cmd_args.out_dir
        last_message_id = 0
        while True:
            links, last_message_id = fetch_link_list(
                host,
                client_token,
                application_id,
                output_dir,
                last_message_id=last_message_id,
                tls=tls,
                port=port,
                timeout=http_connection_timeout,
                limit=fetch_pagination_limit
            )
            if links:
                download_links_via_command(
                    command,
                    links,
                    host,
                    application_token,
                    client_token,
                    priority,
                    title,
                    tls,
                    markdown,
                    port,
                    http_connection_timeout
                )
            print(last_message_id)
            sleep(check_period)
    try:
        main(args)
    except KeyboardInterrupt:
        print()
    exit(0)
