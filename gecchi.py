import os
import shutil
import subprocess
import sys
import json
import time
import datetime
from dataclasses import dataclass

STATUS = 'STATUS'
URL = 'URL'
CATEGORY = 'CATEGORY'

STATUS_UNKNOWN = 'Not Started'
STATUS_DOWNLOADED = 'Downloaded'
STATUS_EXTRACTED = 'Extracted'
STATUS_DONE = 'Done'

CONTENT_FOLDER = 'content'

PASSWORDS = ['⑨']
#ARCHIVE_FORMATS = ['.jpg', '.7z', '.zip', '.rar']
MEDIA_FORMATS = ['.jpg', '.jpeg', '.png', '.mp4', '.mkv', '.mp3', '.wav', '.apk', '.zip', '.7z', '.rar']
MEDIA_RATIO_THRESHOLD = 0.5

@dataclass
class ArchiveInfo:
    is_archive: bool = False
    password_matched: bool = False
    password: str = ''
    volumes: int = -1
    volume_index: int = -1
    media_ratio: float = 0.0

@dataclass
class BtInfo:
    exist: bool = False
    completed: bool = False
    state: str = ''
    size: int = -1
    downloaded_size: int = -1
    progress: float = 0.0
    speed: int = -1
    eta: int = -1
    time_active: int = -1

def read_file(folder: str, name: str, default:str = '') -> str:
    try:
        file = open(os.path.join(folder, name), "r")
    except:
        return default
    content = file.readline()
    file.close()
    return content

def write_file(folder: str, name: str, content:str) -> bool:
    try:
        file = open(os.path.join(folder, name), "w")
    except:
        return False
    file.write(content)
    file.close()
    return True

def execute(cmd: str, quiet=False) -> bool:
    result = subprocess.run(cmd, capture_output=quiet, shell=True)
    return result.returncode == 0

# Returns: (success: bool, stdout: str, stderr:str)
def execute_and_get_output(cmd: str) -> tuple:
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.returncode == 0, result.stdout, result.stderr

def format_bytes(size) -> str:
    power = 2**10
    n = 0
    power_labels = ['', 'K', 'M', 'G', 'T']
    while size > power:
        size /= power
        n += 1
    return f'{size:.1f}{power_labels[n]}B'

def download_mega(url: str, folder: str) -> bool:
    print('Logging out on MEGA...')
    if not execute(f'"{os.path.join(MEGACMD_FOLDER, "mega-logout")}"'):
        return False
    
    print('Loging into MEGA folder...')
    if not execute(f'"{os.path.join(MEGACMD_FOLDER, "mega-login")}" {url}'):
        return False
    
    print('Remote folder contents:')
    if not execute(f'"{os.path.join(MEGACMD_FOLDER, "mega-ls")}" -lh'):
        return False

    print('Downloading files...')
    if not execute(f'"{os.path.join(MEGACMD_FOLDER, "mega-get")}" "*" "{folder}"'):
        return False
    
    print('Archive downloaded.')
    return True

def check_bt(bt_hash: str) -> BtInfo:
    success, msg, err = execute_and_get_output(f'qbt torrent list --format=json')
    if not success:
        print('Failed getting qbittorrent cli to work!')
        exit(-1)
    try:
        data = json.loads(msg)
        ret = BtInfo()
        hash_lower = bt_hash.lower() # qbittorrent returns hash in lower case
        for torrent in data:
            if not torrent['hash'].startswith(hash_lower):
                continue
            return BtInfo(exist=True, completed=torrent['completion_on'] is not None, state=torrent['state'],
                          size=torrent['size'], downloaded_size=torrent['completed'], 
                          progress=torrent['progress'], speed=torrent['dlspeed'], 
                          eta=torrent['eta'], time_active=torrent['time_active'])
        return BtInfo(exist=False)

    except:
        print('Qbittorrent output invalid!')
        exit(-1)

def delete_bt(bt_hash: str) -> bool:
    return execute(f'qbt torrent delete {bt_hash}')

def download_bt_magnet_link(magnet_link: str, folder: str) -> bool:
    # prefix: 20 cahrs, hash: 40 chars
    if not magnet_link.startswith('magnet:?xt=urn:btih:') or not len(magnet_link) >= 60:
        print('Invalid magnet link!')
        return False
    return download_bt(magnet_link, magnet_link[20:60], folder)

def download_bt_hash(bt_hash: str, folder: str) -> bool:
    if len(bt_hash) != 40:
        print('Invalid bt hash!')
        return False
    return download_bt('magnet:?xt=urn:btih:' + bt_hash, bt_hash, folder)

def download_bt(magnet_link: str, bt_hash: str, folder: str) -> bool:
    # Check bt state first
    info = check_bt(bt_hash)
    if info.exist:
        if info.completed:
            print('File download already completed.')
            delete_bt(bt_hash)
            return True
    else:
        print('Starting bt download...')
        if not execute(f'qbt torrent add url "{magnet_link}" --folder "{folder}"'):
            print('Failed starting BT download.')
            return False
    
    while True:
        time.sleep(1.0)
        info = check_bt(bt_hash)
        if not info.exist:
            print('BT download disappeared. Please restart the task.')
            return False
        if info.completed:
            print('Download completed.')
            delete_bt(bt_hash)
            return True
        print(f'{info.state}|{format_bytes(info.downloaded_size)}/{format_bytes(info.size)}|{info.progress * 100:.1f}%|{format_bytes(info.speed)}/s|ETA {datetime.timedelta(seconds=info.eta)}|Active {datetime.timedelta(seconds=info.time_active)}')
    
def get_archive_info(file: str) -> ArchiveInfo:
    ret = ArchiveInfo()
    # For now, allow any file extension
    # match = False
    # for format in ARCHIVE_FORMATS:
    #     if file.endswith(format):
    #         match = True
    #         break
    # if not match:
    #     ret.is_archive = False
    #     return ret
    
    for pswd in PASSWORDS:
        result = subprocess.run(f'"{SEVENZIP_PATH}" l "{file}" -p"{pswd}"', capture_output=True, text=True, shell=True)
        if result.returncode != 0:
            if result.stderr.find('Wrong password?') == -1:
                ret.is_archive = False
                return ret
        else:
            ret.is_archive = True
            ret.password_matched = True
            ret.password = pswd

            # extract info
            lines = result.stdout.splitlines()
            splitters = []
            for i in range(len(lines)):
                if lines[i].startswith('Volumes = '):
                    ret.volumes = int(lines[i][10:])
                elif lines[i].startswith('Volume Index = '):
                    ret.volume_index = int(lines[i][15:])
                elif lines[i].startswith('----------'):
                    splitters.append(i)
            
            total_size = 0
            media_size = 0
            if len(splitters) >= 2:
                for i in range(splitters[0] + 1, splitters[1]):
                    if lines[i][20] == 'D':
                        continue # Is directory

                    size = int(lines[i][25:].split()[0])

                    total_size += size
                    for ext in MEDIA_FORMATS:
                        if lines[i].endswith(ext):
                            media_size += size
                            break
            
            if total_size == 0:
                ret.media_ratio = 0
            else:
                ret.media_ratio = media_size / total_size
            return ret

    ret.is_archive = True
    ret.password_matched = False
    return ret

def extract(file: str, folder: str, password: str) -> bool:
    return execute(f'"{SEVENZIP_PATH}" x "{file}" -p"{password}" -o"{folder}" -aou', quiet=True) # Rename for exiting file

def prompt_for_category() -> str:
    categories = []
    for file in os.listdir(DEST_FOLDER_ROOT):
        if os.path.isdir(os.path.join(DEST_FOLDER_ROOT, file)):
            categories.append(file)
    
    print('Please choose category from below:')
    for i in range(len(categories)):
        print(f'{i + 1}. {categories[i]}')

    while True:
        text = input(f'Enter number (1 ~ {len(categories)}): ')
        try:
            val = int(text)
        except:
            pass
        else:
            if val >= 1 and val <= len(categories):
                print(f'Selected category: {categories[val - 1]}.')
                return categories[val - 1]
        
        print('Invalid choice.')

class Task:
    def initialize_new(self, ws, name, url, category) -> bool:
        self.folder = os.path.join(ws, name)
        self.content_folder = os.path.join(ws, name, CONTENT_FOLDER)
        self.name = name

        if not os.path.exists(self.folder):
            print(f'Task folder [{name}] not exist.')
            return False
        
        if not os.path.exists(self.content_folder):
            os.mkdir(self.content_folder)

        self.__update_status(STATUS_UNKNOWN)
        self.set_url(url)
        self.set_category(category)
        return True

    def initialize_load(self, ws, name) -> bool:
        self.folder = os.path.join(ws, name)
        self.content_folder = os.path.join(ws, name, CONTENT_FOLDER)
        self.name = name

        if not os.path.exists(self.folder):
            print(f'Task folder [{name}] not exist.')
            return False
        
        if not os.path.exists(self.content_folder):
            os.mkdir(self.content_folder)
        
        status_file_path = os.path.join(self.folder, STATUS)
        if os.path.exists(status_file_path):
            status_file = open(status_file_path)
            self.status = status_file.readline()
            status_file.close()
        else:
            self.__update_status(STATUS_UNKNOWN)
        
        url_file_path = os.path.join(self.folder, URL)
        if not os.path.exists(url_file_path):
            print('Could not load URL.')
            return False
        
        url_file = open(url_file_path)
        self.url = url_file.readline()
        url_file.close()

        category_file_path = os.path.join(self.folder, CATEGORY)
        if not os.path.exists(category_file_path):
            print('Could not load category.')
            return False
        
        category_file = open(category_file_path)
        self.category = category_file.readline()
        category_file.close()
        
        return True
    
    def delete(self):
        if os.path.exists(self.folder):
            shutil.rmtree(self.folder)

    def set_url(self, url):
        self.url = url
        url_file_path = os.path.join(self.folder, URL)
        url_file = open(url_file_path, 'w')
        url_file.write(url)
        url_file.close()

    def set_category(self, category):
        self.category = category
        category_file_path = os.path.join(self.folder, CATEGORY)
        category_file = open(category_file_path, 'w')
        category_file.write(category)
        category_file.close()

    def __update_status(self, status):
        self.status = status
        status_file_path = os.path.join(self.folder, STATUS)
        status_file = open(status_file_path, 'w')
        status_file.write(status)
        status_file.close()

    def download(self) -> bool:
        if self.status != STATUS_UNKNOWN:
            print(f'Archive already downloaded for task {self.name}.')
            return False
        
        # Determine type of link
        if self.url.startswith('https://mega.nz'):
            if not download_mega(self.url, self.content_folder):
                return False
        elif self.url.startswith('magnet:'):
            if not download_bt_magnet_link(self.url, self.content_folder):
                return False
        elif len(self.url) == 40:
            if not download_bt_hash(self.url, self.content_folder):
                return False
        else:
            print(f'Unknown URL: {self.url}')
            return False
        
        self.__update_status(STATUS_DOWNLOADED)
        return True
        
    def extract(self) -> bool:
        if self.status != STATUS_DOWNLOADED:
            print(f'Cannot perform extract when status is [{self.status}].')
            return False
        
        while True:
            files = os.listdir(self.content_folder)

            # Handle single folder case
            if len(files) == 1:
                single_folder_path = os.path.join(self.content_folder, files[0])
                if os.path.isdir(single_folder_path):
                    p = os.path.join(self.content_folder, '_SINGLE_FOLDER_')
                    shutil.move(single_folder_path, p) # rename folder, to avoid the inner files have same name
                    for f in os.listdir(p):
                        shutil.move(os.path.join(p, f), self.content_folder)
                    os.remove(p)
                    continue # Go to next iteration

            files_extracted = False
            to_remove = []
            for file_name in files:
                file_path = os.path.join(self.content_folder, file_name)
                if os.path.isfile(file_path):
                    info = get_archive_info(file_path)
                    if info.is_archive:
                        if info.media_ratio < MEDIA_RATIO_THRESHOLD:
                            print(f'Not extracting [{file_name}], media ratio {info.media_ratio * 100:.1f}%')
                            continue
                        to_remove.append(file_path)
                        if info.volumes > 1 and info.volume_index != 0:
                            continue
                        if info.password_matched:
                            print(f'Extracting [{file_name}], media ratio {info.media_ratio * 100:.1f}%...')
                            if not extract(file_path, self.content_folder, info.password):
                                print(f'Failed extracting file [{file_name}].')
                                return False
                            else:
                                files_extracted = True
                        else:
                            while True:
                                pswd = input(f'Please enter password for archive [{file_name}], or "skip" to skip extracting: ')
                                if pswd == 'skip':
                                    break
                                if extract(file_path, self.content_folder, pswd):
                                    files_extracted = True
                                    break
                                print('Password incorect, please try again.')
            
            for file_path in to_remove:
                #os.remove(file_path)
                shutil.move(file_path, self.folder) # Move to outer side rather than deleting
            if not files_extracted:
                self.__update_status(STATUS_EXTRACTED)
                return True
            
    def copy(self):
        if self.status != STATUS_EXTRACTED:
            print(f'Cannot perform copy when status is [{self.status}].')
            return False
        
        category_folder = os.path.join(DEST_FOLDER_ROOT, self.category)
        if not os.path.isdir(category_folder):
            print(f'Category not exist: {self.category}')
            return False
        
        dest_folder = os.path.join(category_folder, self.name)
        if not os.path.exists(dest_folder):
            os.mkdir(dest_folder)
        elif not os.path.isdir(dest_folder):
            print(f'Name already exists as a file: {dest_folder}')
            return False
        
        for file in os.listdir(self.content_folder):
            file_path = os.path.join(self.content_folder, file)
            print(f'Copying [{file}]...')
            if os.name == 'nt':
                result = execute(f'xcopy "{file_path}" "{dest_folder}" /E/H/Y', quiet=True)
            else:
                result = execute(f'cp -r "{file_path}" "{dest_folder}"', quiet=True)
            if not result:
                print(f'Failed copying [{file}].')
                return False
        print(f'Done copying to [{dest_folder}].')
            
        self.__update_status(STATUS_DONE)
        return True
    
    def run(self) -> bool:
        if self.status == STATUS_UNKNOWN:
            return self.download() and self.extract() and self.copy()
        elif self.status == STATUS_DOWNLOADED:
            return self.extract() and self.copy()
        elif self.status == STATUS_EXTRACTED:
            return self.copy()
        elif self.status == STATUS_DONE:
            return True
        else:
            return False

# Returns whether need again
def task_operations(task: Task) -> bool:
    print('==============================================')
    print(f'Selected task: {task.name}')
    print(f'Status: {task.status}')
    print(f'URL: {task.url}')
    print(f'Category: {task.category}')
    print('')
    print('Options: ')
    print('1. Run/Resume')
    print('2. Set URL')
    print('3. Set category')
    print('4. Delete')
    print('5. Exit')
    print('')

    text = input('Select one option (1 ~ 5), default 1 (Run/Resume): ')
    if text == '1' or text == '':
        if task.run():
            print('Gecchi success!')
            if input('Do you want to preserve temp files? Enter "y" to preserve: ') == 'y':
                print('Task preserved.')
                return True
            else:
                task.delete()
                print('Task deleted. Exitting.')
                return False
        else:
            print(f'Running failed. Status: {task.status}. Please check logs and temp files.')
            return True
    elif text == '2':
        task.set_url(input('Enter new URL: '))
        print('URL set.')
        return True
    elif text == '3':
        task.set_category(prompt_for_category())
        print('Category set.')
        return True
    elif text == '4':
        if input('Enter "y" to confirm delete: ') == 'y':
            task.delete()
            print('Task deleted.')
            return False
        else:
            print('Cancel delete.')
            return True
    elif text == '5':
        print('Exitting.')
        return False
    else:
        print('Unknown choice.')
        return True

def get_current_tasks() -> list:
    tasks = []
    for file in os.listdir(WORKSPACE):
        if os.path.isdir(os.path.join(WORKSPACE, file)):
            task = Task()
            if task.initialize_load(WORKSPACE, file):
                tasks.append(task)
            else:
                shutil.rmtree(os.path.join(WORKSPACE, file))
    return tasks

def new_task() -> Task:
    task = Task()
    while True:
        name = input('Enter new ecchi name: ')
        if os.path.exists(os.path.join(WORKSPACE, name)):
            print('Task with this name already exists.')
            continue
        try:
            os.mkdir(os.path.join(WORKSPACE, name))
        except:
            print('Name invalid for file. Please note that special characters like :/\\|*?"<> are not allowed.')
            continue

        break

    task.initialize_new(WORKSPACE, name, input('Enter ecchi URL: '), prompt_for_category()) # Assuming not failing
    return task

# SEVENZIP_PATH = '7z'
# print(get_archive_info('C:\\Users\\wjw11\\Downloads\\gecchi_ws\\兄.7z'))
# exit(0)

# Check args
if len(sys.argv) < 3:
    print('Usage: gecchi.py [workspace] [dest_folder_root]')
    exit(-1)

WORKSPACE = sys.argv[1]
DEST_FOLDER_ROOT = sys.argv[2]
if not os.path.isdir(WORKSPACE):
    print(f'Provided workspace does not exist: {WORKSPACE}')
    exit(-1)
if not os.path.isdir(DEST_FOLDER_ROOT):
    print(f'Provided dest folder root does not exist: {DEST_FOLDER_ROOT}')
    exit(-1)

# Check environment
print('NOTE: You can set 7z and mega path by setting SEVENZIP_PATH and MEGACMD_FOLDER environment variables.')
if os.name == 'nt':
    SEVENZIP_PATH = '7z.exe'
else:
    SEVENZIP_PATH = '7zz'

MEGACMD_FOLDER = ''

env_7z_path = os.environ.get('SEVENZIP_PATH', '')
if env_7z_path != '':
    SEVENZIP_PATH = env_7z_path
    print(f'Using 7z path from env: {env_7z_path}')

env_mega_path = os.environ.get('MEGACMD_FOLDER', '')
if env_mega_path != '':
    MEGACMD_FOLDER = env_mega_path
    print(f'Using megacmd folder path from env: {env_mega_path}')

# Print tasks first
tasks = get_current_tasks()

if len(tasks) == 0:
    print('No existing task found.')
else:
    print('Current gecchi tasks:')
    for i in range(len(tasks)):
        print(f'{i + 1}: [{tasks[i].status}] {tasks[i].name}')
        
while True:
    text = input(f'Select a task to check (1 ~ {len(tasks)}) or enter nothing for a new task: ')
    if text == '':
        task = new_task()
        break
    else:
        try:
            val = int(text)
        except:
            print('Invalid choice.')
            continue
        else:
            if val >= 1 and val <= len(tasks):
                task = tasks[val - 1]
            else:
                print('Index out of range.')
                continue
        break
        
while (task_operations(task)):
    pass

exit(0)
