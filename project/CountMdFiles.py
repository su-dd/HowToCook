import os

def count_md_files():
    directories = [
        'd:\\workspace\\HowToCook\\dishes',
        'd:\\workspace\\HowToCook\\tips'
    ]
    
    count = 0
    for directory in directories:
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith('.md'):
                    count += 1
    
    print(f'Total .md files: {count}')

if __name__ == '__main__':
    count_md_files()