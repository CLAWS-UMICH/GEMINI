import os

def main():
    base_dir = 'data/twotools'
    if not os.path.exists(base_dir):
        print("Dir not found")
        return
        
    doubles = []
    for f in os.listdir(base_dir):
        if 'AND' in f:
            parts = f.replace('.jsonc', '').split('AND')
            if len(parts) == 2:
                if parts[0] == parts[1]:
                    doubles.append(f)
    
    print(f"Found {len(doubles)} double-tool files.")
    for d in doubles:
        print(d)

if __name__ == '__main__':
    main()
