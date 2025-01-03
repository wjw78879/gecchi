import os
import shutil
import subprocess
import sys

STATUS = 'STATUS'
URL = 'URL'
CATEGORY = 'CATEGORY'
STATUS_UNKNOWN = 'Not Started'
STATUS_DOWNLOADED = 'Downloaded'
STATUS_EXTRACTED = 'Extracted'
STATUS_DONE = 'Done'

CONTENT_FOLDER = 'content'

PASSWORDS = ['⑨']

def execute(cmd: str, quiet=False) -> bool:
    result = subprocess.run(cmd, capture_output=not quiet, text=True, shell=True)
    if not quiet:
        print(result.stdout)
        print(result.stderr)
    return result.returncode == 0

def download_mega(url: str, folder: str) -> bool:
    print('Logging out on MEGA...')
    if not execute(f'"{os.path.join(MEGACMD_FOLDER, "mega-logout.bat")}"'):
        return False
    
    print('Loging into MEGA folder...')
    if not execute(f'"{os.path.join(MEGACMD_FOLDER, "mega-login.bat")}" {url}'):
        return False

    print('Downloading files...')
    if not execute(f'"{os.path.join(MEGACMD_FOLDER, "mega-get.bat")}" * "{folder}"'):
        return False
    
    print('Archive downloaded.')
    return True

def is_archive(file: str) -> bool:
    result = subprocess.run(f'"{SEVENZIP_PATH}" l "{file}" -p""', capture_output=True, text=True, shell=True)
    if result.returncode == 0:
        return True
    elif result.stderr.find('Wrong password?') != -1:
        return True

def extract(file: str, folder: str) -> bool:
    for pswd in PASSWORDS:
        if execute(f'"{SEVENZIP_PATH}" e "{file}" -p"{pswd}" -o"{folder}" -y', quiet=True):
            return True
    return False

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
            if download_mega(self.url, self.content_folder):
                self.__update_status(STATUS_DOWNLOADED)
                return True
            return False
        else:
            print(f'Unknown URL: {self.url}')
            return False
        
    def extract(self) -> bool:
        if self.status != STATUS_DOWNLOADED:
            print(f'Cannot perform extract when status is [{self.status}].')
            return False
        
        while True:
            has_archive = False
            for file_name in os.listdir(self.content_folder):
                file_path = os.path.join(self.content_folder, file_name)
                if os.path.isfile(file_path) and is_archive(file_path):
                    has_archive = True
                    if not extract(file_path, self.content_folder):
                        print(f'Failed extracting file [{file_name}]. Maybe password incorrect?')
                        return False
                    os.remove(file_path) # Remove after successfull extraction
            if not has_archive:
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
            try:
                if os.path.isdir(file_path):
                    shutil.copytree(file_path, dest_folder)
                else:
                    shutil.copy(file_path, dest_folder)
            except:
                print(f'Failed copying [{file}].')
                return False
            
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

    text = input('Select one option (1 ~ 5): ')
    if text == '1':
        if task.run():
            print('Gecchi success! Clearing temp.')
            task.delete()
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

# Check args
if len(sys.argv) < 3:
    print('Usage: gecchi.py [workspace] [dest_folder_root]')
    exit(-1)

WORKSPACE = sys.argv[1]
DEST_FOLDER_ROOT = sys.argv[2]
if not os.path.isdir(WORKSPACE):
    print('Provided workspace does not exist.')
    exit(-1)
if not os.path.isdir(DEST_FOLDER_ROOT):
    print('Provided dest folder root does not exist.')
    exit(-1)

# Check environment
print('NOTE: You can set 7z and mega path by setting SEVENZIP_PATH and MEGACMD_FOLDER environment variables.')
SEVENZIP_PATH = '7z.exe'
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
tasks = []
for file in os.listdir(WORKSPACE):
    if os.path.isdir(os.path.join(WORKSPACE, file)):
        task = Task()
        if task.initialize_load(WORKSPACE, file):
            tasks.append(task)
        else:
            shutil.rmtree(os.path.join(WORKSPACE, file))

print('Current gecchi tasks:')
if len(tasks) == 0:
    print('No task found.')
else:
    for i in range(len(tasks)):
        print(f'{i + 1}: [{tasks[i].status}] {tasks[i].name}')
        
while True:
    text = input(f'Select a task to check (1 ~ {len(tasks)}) or enter "n" for a new task: ')
    if text == 'n':
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
