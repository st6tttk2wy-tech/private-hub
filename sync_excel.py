import openpyxl
import shutil
from datetime import datetime

def sync_excel_files():
    source = 'F:\\360MoveData\\Users\\0000\\Desktop\\1.xlsx'
    target = 'F:\\360MoveData\\Users\\0000\\Desktop\\1 - 副本.xlsx'
    
    try:
        # 复制源文件到目标文件
        shutil.copy2(source, target)
        print(f'同步完成: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        print(f'源文件: {source}')
        print(f'目标文件: {target}')
        return True
    except Exception as e:
        print(f'同步失败: {e}')
        return False

if __name__ == '__main__':
    sync_excel_files()