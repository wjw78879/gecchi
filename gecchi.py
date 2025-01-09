import os
import shutil
import subprocess
import sys
import json
import time
import datetime
import readline
from baidu_share import BaiDuPan
from dataclasses import dataclass

STATUS = 'STATUS'
URL = 'URL'
CATEGORY = 'CATEGORY'

STATUS_UNKNOWN = 'Not Started'
STATUS_DOWNLOADED = 'Downloaded'
STATUS_EXTRACTED = 'Extracted'
STATUS_DONE = 'Done'

CONTENT_FOLDER = 'content'
TEMP_FOLDER = 'temp'

CATEGORIES = {}
PASSWORDS = ['⑨', '米粒儿']
#ARCHIVE_FORMATS = ['.jpg', '.7z', '.zip', '.rar']
MEDIA_FORMATS = ['.jpg', '.jpeg', '.png', '.mp4', '.mkv', '.mp3', '.wav', '.apk', '.zip', '.7z', '.rar']
MEDIA_RATIO_THRESHOLD = 0.5
ARCHIVE_FILECOUNT_THRESHOLD = 10

@dataclass
class ArchiveInfo:
    is_archive: bool = False
    password_matched: bool = False
    password: str = ''
    volumes: int = -1
    volume_index: int = -1
    file_count: int = 0
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
        file = open(os.path.join(folder, name), "r", encoding='utf-8')
    except:
        return default
    content = file.readline()
    file.close()
    return content

def write_file(folder: str, name: str, content:str) -> bool:
    try:
        file = open(os.path.join(folder, name), "w", encoding='utf-8')
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
    
    print('NOTE: BT download will run in background. You can close gecchi now and check progress later.')
    while True:
        time.sleep(1.0)
        info = check_bt(bt_hash)
        if not info.exist:
            print('\nBT download disappeared. Please restart the task.')
            return False
        if info.completed:
            print('\nDownload completed.')
            delete_bt(bt_hash)
            return True
        print(f'{info.state}|{format_bytes(info.downloaded_size)}/{format_bytes(info.size)}|{info.progress * 100:.1f}%|{format_bytes(info.speed)}/s|ETA {datetime.timedelta(seconds=info.eta)}|Active {datetime.timedelta(seconds=info.time_active)}\r', end='')

def download_baidu(url: str, name: str, folder: str) -> bool:
    print('Making remote dir...')
    if not execute(f'bypy mkdir "{name}"'):
        print('Failed making dir. Maybe bypy is not available?')
        return False

    print('Transferring share...')
    bd = BaiDuPan(BDUSS, STOKEN)
    path = f'/apps/bypy/{name}/'
    pos = url.find('?pwd=')
    if pos != -1:
        res = bd.saveShare(url[:pos], url[pos + 5:], path)
    else:
        res = bd.saveShare(url, None, path)
    if res['errno'] != 0:
        print('Failed transferring Baidu files. Info: ' + str(res))
        return False
    
    print('Downloading files...')
    if not execute(f'bypy downdir "{name}" "{folder}"'):
        return False
    
    print('Download finished, but there might be errors.')
    return True

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
            if result.stderr.find('Wrong password') != -1:
                continue
            if result.stderr.find('Cannot open the file as archive') != -1:
                ret.is_archive = False
                return ret
            
        ret.password_matched = True
        ret.password = pswd
        break
    
    ret.is_archive = True
    if not ret.password_matched:
        while True:
            pswd = input(f'Please enter password for archive [{file}], or "skip" to skip extracting: ')
            if pswd == 'skip':
                return ret
            result = subprocess.run(f'"{SEVENZIP_PATH}" l "{file}" -p"{pswd}"', capture_output=True, text=True, shell=True)
            if result.returncode == 0 or result.stderr.find('Wrong password') == -1:
                print('Password correct.')
                ret.password_matched = True
                ret.password = pswd
                PASSWORDS.append(pswd) # Add to global password list if success
                break
            print('Password incorrect, please try again.')

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

            ret.file_count += 1
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

def move_all_files(src_folder: str, dest_folder: str):
    for file in os.listdir(src_folder):
        file_path = os.path.join(src_folder, file)
        try:
            shutil.move(file_path, dest_folder)
        except:
            dot_pos = file.rfind('.')
            if dot_pos == -1:
                name = file
                ext = ''
            else:
                name = file[:dot_pos]
                ext = file[dot_pos:]
            number = 1
            while True:
                new_name = f'{name}_{number}{ext}'
                new_path = os.path.join(dest_folder, new_name)
                if not os.path.exists(new_path):
                    print(f'File already exists, renaming to [{new_name}].')
                    shutil.move(file_path, new_path)
                    break
                number += 1

def remove_all_files(folder: str):
    if len(os.listdir(folder)) == 0:
        return
    shutil.rmtree(folder)
    os.mkdir(folder)

# Returns: (success, extracted)
def extract(file: str, folder: str, password: str, temp_folder: str) -> tuple:
    # The -aou option enables renaming for exiting file
    # Update: Not using -aou, assuming the temp folder is empty.
    success, stdout, stderr = execute_and_get_output(f'"{SEVENZIP_PATH}" x "{file}" -p"{password}" -o"{temp_folder}"')
    if success:
        move_all_files(temp_folder, folder)
        return True, True
    
    remove_all_files(temp_folder)
    if stderr.find('Wrong password') != -1:
        # This is the case when some format (like 7z) needs password on extraction but not listing.
        # We try the password list first, then prompt for a password.
        for pswd in PASSWORDS:
            success, stdout, stderr = execute_and_get_output(f'"{SEVENZIP_PATH}" x "{file}" -p"{pswd}" -o"{temp_folder}"')
            if success:
                move_all_files(temp_folder, folder)
                return True, True
            remove_all_files(temp_folder)
            if stderr.find('Wrong password') == -1:
                print('Extraction error:')
                print(stdout)
                print(stderr)
                return False, False
                
        while True:
            pswd = input(f'Please enter password for archive [{file}], or "skip" to skip extracting: ')
            if pswd == 'skip':
                print('Skipping extraction.')
                return True, False
            print('Extracting...')
            success, stdout, stderr = execute_and_get_output(f'"{SEVENZIP_PATH}" x "{file}" -p"{pswd}" -o"{temp_folder}"')
            if success:
                print('Password correct, extraction success.')
                PASSWORDS.append(pswd) # Add to global password list if success
                move_all_files(temp_folder, folder)
                return True, True
            remove_all_files(temp_folder)
            if stderr.find('Wrong password') != -1:
                break # Error

            print('Password incorrect, please try again.')

    print('Extraction error:')
    print(stdout)
    print(stderr)
    return False, False

def prompt_for_category() -> str:
    categories = list(CATEGORIES.keys())
    
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
        self.temp_folder = os.path.join(ws, name, TEMP_FOLDER)
        self.name = name

        if not os.path.exists(self.folder):
            print(f'Task folder [{name}] not exist.')
            return False
        
        if not os.path.exists(self.content_folder):
            os.mkdir(self.content_folder)

        if not os.path.exists(self.temp_folder):
            os.mkdir(self.temp_folder)

        self.set_status(STATUS_UNKNOWN)
        self.set_url(url)
        self.set_category(category)
        return True

    def initialize_load(self, ws, name) -> bool:
        self.folder = os.path.join(ws, name)
        self.content_folder = os.path.join(ws, name, CONTENT_FOLDER)
        self.temp_folder = os.path.join(ws, name, TEMP_FOLDER)
        self.name = name

        if not os.path.exists(self.folder):
            print(f'Task folder [{name}] not exist.')
            return False
        
        if not os.path.exists(self.content_folder):
            os.mkdir(self.content_folder)

        if not os.path.exists(self.temp_folder):
            os.mkdir(self.temp_folder)
        
        status_file_path = os.path.join(self.folder, STATUS)
        if not os.path.exists(status_file_path):
            print('Could not load status.')
            return False
        self.status = read_file(self.folder, STATUS)
        
        url_file_path = os.path.join(self.folder, URL)
        if not os.path.exists(url_file_path):
            print('Could not load URL.')
            return False
        self.url = read_file(self.folder, URL)

        category_file_path = os.path.join(self.folder, CATEGORY)
        if not os.path.exists(category_file_path):
            print('Could not load category.')
            return False
        self.category = read_file(self.folder, CATEGORY)
        
        return True
    
    def delete(self):
        if os.path.exists(self.folder):
            shutil.rmtree(self.folder)

    def reset(self):
        if os.path.exists(self.folder):
            shutil.rmtree(self.folder)
        os.mkdir(self.folder)
        self.set_status(STATUS_UNKNOWN)
        self.set_url(self.url)
        self.set_category(self.category)

    def set_status(self, status):
        self.status = status
        write_file(self.folder, STATUS, status)

    def set_url(self, url):
        self.url = url
        write_file(self.folder, URL, url)

    def set_category(self, category):
        self.category = category
        write_file(self.folder, CATEGORY, category)

    def download(self) -> bool:
        if self.status != STATUS_UNKNOWN:
            print(f'Archive already downloaded for task {self.name}.')
            return False
        
        # Determine type of link
        if self.url.startswith('https://mega.nz/folder/'):
            if not download_mega(self.url, self.content_folder):
                return False
        elif self.url.startswith('https://pan.baidu.com/s/'):
            if not download_baidu(self.url, self.name, self.content_folder):
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
        
        self.set_status(STATUS_DOWNLOADED)
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
                    print(f'Expanding single folder [{files[0]}]...')
                    p = os.path.join(self.content_folder, '_SINGLE_FOLDER_')
                    shutil.move(single_folder_path, p) # rename folder, to avoid the inner files have same name
                    for f in os.listdir(p):
                        shutil.move(os.path.join(p, f), self.content_folder)
                    shutil.rmtree(p)
                    continue # Go to next iteration

            files_extracted = False
            to_remove = []
            for file_name in files:
                file_path = os.path.join(self.content_folder, file_name)
                if os.path.isfile(file_path):
                    info = get_archive_info(file_path)
                    if info.is_archive:
                        if not info.password_matched:
                            print(f'Skipping extracting archive [{file_name}]. Password unknown.')
                            continue
                        if info.media_ratio < MEDIA_RATIO_THRESHOLD and info.file_count > ARCHIVE_FILECOUNT_THRESHOLD:
                            print(f'Not extracting [{file_name}], media ratio {info.media_ratio * 100:.1f}%, file count {info.file_count}')
                            continue
                        to_remove.append(file_path)
                        if info.volume_index > 0:
                            continue
                        print(f'Extracting [{file_name}], media ratio {info.media_ratio * 100:.1f}%, file count {info.file_count}...')
                        success, extracted = extract(file_path, self.content_folder, info.password, self.temp_folder)
                        if not success:
                            print(f'Failed extracting file [{file_name}].')
                            return False
                        if extracted:
                            files_extracted = True
            
            for file_path in to_remove:
                #os.remove(file_path)
                shutil.move(file_path, self.folder) # Move to outer side rather than deleting
            if not files_extracted:
                self.set_status(STATUS_EXTRACTED)
                return True
            
    def copy(self):
        if self.status != STATUS_EXTRACTED:
            print(f'Cannot perform copy when status is [{self.status}].')
            return False
        
        category_folder = CATEGORIES.get(self.category, '')
        if category_folder == '':
            print(f'Category not exist: {self.category}')
            return False
        
        dest_folder = os.path.join(category_folder, self.name)
        if not os.path.exists(dest_folder):
            os.mkdir(dest_folder)
        elif not os.path.isdir(dest_folder):
            print(f'Name already exists as a file: {dest_folder}')
            return False
        
        print('Copying files to category folder...')
        for file in os.listdir(self.content_folder):
            file_path = os.path.join(self.content_folder, file)
            #print(f'Copying [{file}]...')
            if os.name == 'nt':
                result = execute(f'xcopy "{file_path}" "{dest_folder}" /E/H/Y', quiet=True)
            else:
                result = execute(f'cp -r "{file_path}" "{dest_folder}"', quiet=True)
            if not result:
                print(f'Failed copying [{file}].')
                return False
        print(f'Finished copying files.')
            
        self.set_status(STATUS_DONE)
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
        
    def run_one_stage(self) -> bool:
        if self.status == STATUS_UNKNOWN:
            return self.download()
        elif self.status == STATUS_DOWNLOADED:
            return self.extract()
        elif self.status == STATUS_EXTRACTED:
            return self.copy()
        elif self.status == STATUS_DONE:
            return True
        else:
            return False

# Returns whether need again
def ensure_executables() -> bool:
    if not execute(f'{SEVENZIP_PATH}', True):
        print(f'Error: 7z executable ({SEVENZIP_PATH}) not available. You may set 7z path in SEVENZIP_PATH environment variable.')
        return False
    
    if not execute(f'{os.path.join(MEGACMD_FOLDER, "mega-help")}', True):
        print(f'Warning: MEGAcmd not found (current folder: {MEGACMD_FOLDER}). Mega links cannot work. You may set MEGAcmd folder in MEGACMD_FOLDER environment variable.')
    
    if not execute('qbt', True):
        print('Warning: qbt not found. Magnet links cannot work.')
    
    if not execute('bypy -h', True):
        print('Warning: bypy not found. Baidu share links cannot work.')
    
    return True

def read_categories() -> bool:
    file_path = os.path.join(WORKSPACE, 'categories.txt')
    if not os.path.isfile(file_path):
        print(f'"categories.txt" not found in workspace: {WORKSPACE}. Please create one and list categories.')
        print('Each line in this file should be "CATEGORY:PATH". e.g. "Anime:/mnt/nas/anime"')
        return False
    file = open(file_path, encoding='utf-8')
    lines = file.readlines()
    file.close()

    for line in lines:
        if line.strip() == '':
            continue
        pos = line.find(':')
        if pos == -1 or pos == len(line) - 1:
            print(f'Error reading category line: {line}')
            print('Each line should be "CATEGORY:FOLDER". e.g. "Anime:/mnt/nas/anime"')
            return False
        cat = line[:pos].strip()
        folder = line[pos + 1:].strip()
        if cat == '':
            print(f'Missing category name in line: {line}')
            return False
        if not os.path.isdir(folder):
            print(f'Folder not exist in category line: {line}')
            return False
        CATEGORIES[cat] = folder
    print(f'Successfully read {len(CATEGORIES)} categories.')
    return True

def task_operations(task: Task) -> bool:
    print('==============================================')
    print(f'Selected task: {task.name}')
    print(f'Status: {task.status}')
    print(f'URL: {task.url}')
    print(f'Category: {task.category}')
    print('')
    print('Options: ')
    print('1. Run/Resume')
    if task.status == STATUS_UNKNOWN:
        print('2. Run next stage: Download')
    elif task.status == STATUS_DOWNLOADED:
        print('2. Run next stage: Extract')
    elif task.status == STATUS_EXTRACTED:
        print('2. Run next stage: Copy')
    elif task.status == STATUS_DONE:
        print('2. Run next stage: None')
    else:
        print('2. Run next stage: ???')
    print('3. Set URL')
    print('4. Set category')
    print('5. Set status')
    print('6. Reset')
    print('7. Delete')
    print('8. Exit')
    print('')

    text = input('Select one option (1 ~ 8), default 1 (Run/Resume): ')
    if text == '1' or text == '':
        if task.run():
            print('Gecchi success!')
            if input('Do you want to retain temp files? Enter "y" to retain (default not retaining): ') == 'y':
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
        if task.run_one_stage():
            print('Gecchi one stage success.')
        else:
            print('Gecchi one stage failed. Please check logs and temp files.')
        return True
    elif text == '3':
        task.set_url(input('Enter new URL: '))
        print('URL set.')
        return True
    elif text == '4':
        task.set_category(prompt_for_category())
        print('Category set.')
        return True
    elif text == '5':
        print('Choose target status:')
        print(f'1. {STATUS_UNKNOWN}')
        print(f'2. {STATUS_DOWNLOADED}')
        print(f'3. {STATUS_EXTRACTED}')
        print(f'4. {STATUS_DONE}')
        t = input('Enter option (1 ~ 4), or other to cancel: ')
        if t == '1':
            task.set_status(STATUS_UNKNOWN)
            print(f'Set status to: {STATUS_UNKNOWN}.')
            return True
        elif t == '2':
            task.set_status(STATUS_DOWNLOADED)
            print(f'Set status to: {STATUS_DOWNLOADED}.')
            return True
        elif t == '3':
            task.set_status(STATUS_EXTRACTED)
            print(f'Set status to: {STATUS_EXTRACTED}.')
            return True
        elif t == '4':
            task.set_status(STATUS_DONE)
            print(f'Set status to: {STATUS_DONE}.')
            return True
        else:
            print('Cancel setting status.')
            return True
    elif text == '6':
        if input('This will remove all current temp files and reset state. Confirm? (y/N): ') == 'y':
            task.reset()
            print('Task reset.')
        else:
            print('Cancel reset.')
        return True
    elif text == '7':
        if input('Enter "y" to confirm delete: ') == 'y':
            task.delete()
            print('Task deleted.')
            return False
        else:
            print('Cancel delete.')
            return True
    elif text == '8':
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
                print(f'Failed loading task folder: {file}')
                #shutil.rmtree(os.path.join(WORKSPACE, file))
    return tasks

def new_task() -> Task:
    task = Task()
    while True:
        name = input('Enter name of the new task (this will be its folder name): ')
        if os.path.exists(os.path.join(WORKSPACE, name)):
            print('Task with this name already exists.')
            continue

        invalid = False
        for char in ':/\\|*?"<>':
            if char in name:
                print('Name invalid for file. Please note that special characters like :/\\|*?"<> are not allowed.')
                invalid = True
                break
        if invalid:
            continue

        try:
            os.mkdir(os.path.join(WORKSPACE, name))
        except:
            print('Name invalid for file. Please note that special characters like :/\\|*?"<> are not allowed.')
            continue

        break

    task.initialize_new(WORKSPACE, name, input('Enter download URL: '), prompt_for_category()) # Assuming not failing
    return task

# Check args
if len(sys.argv) < 2:
    print('Usage: gecchi.py [workspace]')
    exit(-1)

WORKSPACE = sys.argv[1]
if not os.path.isdir(WORKSPACE):
    print(f'Provided workspace does not exist: {WORKSPACE}')
    exit(-1)
if not read_categories():
    exit(-1)

# Check environment
if os.name == 'nt':
    SEVENZIP_PATH = os.environ.get('SEVENZIP_PATH', '7z.exe')
else:
    SEVENZIP_PATH = os.environ.get('SEVENZIP_PATH', '7zz')

MEGACMD_FOLDER = os.environ.get('MEGACMD_FOLDER', '')

if not ensure_executables():
    exit(-1)

BDUSS = os.environ.get('BDUSS', '')
STOKEN = os.environ.get('STOKEN', '')
if BDUSS == '' or STOKEN == '':
    print('Warning: "BDUSS" or "STOKEN" environment variable not set. Baidu download will be unavailable.')

# Print tasks first
tasks = get_current_tasks()

if len(tasks) == 0:
    print('No existing task found.')
else:
    print('Current gecchi tasks:')
    for i in range(len(tasks)):
        print(f'{i + 1}: [{tasks[i].status}] {tasks[i].name}')
        
while True:
    if len(tasks) == 0:
        text = ''
    else:
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
