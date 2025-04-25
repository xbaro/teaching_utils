import re

# TODO: Update using the codes from Accents in Moodle. See clean_filename in SubmissionSet class
# functions to detect/fix double-encoded UTF-8 strings
# Based on http://blogs.perl.org/users/chansen/2010/10/coping-with-double-encoded-utf-8.html
DOUBLE_ENCODED = re.compile("""
\xC3 (?: [\x82-\x9F] \xC2 [\x80-\xBF]                                    # U+0080 - U+07FF
       |  \xA0       \xC2 [\xA0-\xBF] \xC2 [\x80-\xBF]                   # U+0800 - U+0FFF
       | [\xA1-\xAC] \xC2 [\x80-\xBF] \xC2 [\x80-\xBF]                   # U+1000 - U+CFFF
       |  \xAD       \xC2 [\x80-\x9F] \xC2 [\x80-\xBF]                   # U+D000 - U+D7FF
       | [\xAE-\xAF] \xC2 [\x80-\xBF] \xC2 [\x80-\xBF]                   # U+E000 - U+FFFF
       |  \xB0       \xC2 [\x90-\xBF] \xC2 [\x80-\xBF] \xC2 [\x80-\xBF]  # U+010000 - U+03FFFF
       | [\xB1-\xB3] \xC2 [\x80-\xBF] \xC2 [\x80-\xBF] \xC2 [\x80-\xBF]  # U+040000 - U+0FFFFF
       |  \xB4       \xC2 [\x80-\x8F] \xC2 [\x80-\xBF] \xC2 [\x80-\xBF]  # U+100000 - U+10FFFF
       )
""", re.X)

def is_double_encoded(s):
    return DOUBLE_ENCODED.search(s) and True or False

def decode_double_encoded(m):
    s = m.group(0)
    s = re.sub(r'[\xC2-\xC3]', '', s)
    s = re.sub(r'\A(.)', lambda m: chr(0xC0 | (ord(m.group(1)) & 0x3F)), s)
    return s

def fix_double_encoded(s):
    if not is_double_encoded(s):
        return s
    return DOUBLE_ENCODED.sub(decode_double_encoded, s)

def replace_file_keys(file_path: str, values: dict, start_key: str = '', end_key: str = ''):
    """
    Replace all keys in `values` found in the file at `file_path` with their corresponding values.
    Keys are wrapped with optional `start_key` and `end_key` to allow placeholder formatting.
    Example: If start_key='{{', end_key='}}', a key 'name' will match '{{name}}'.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        for key, value in values.items():
            content = content.replace(f'{start_key}{key}{end_key}', value)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
