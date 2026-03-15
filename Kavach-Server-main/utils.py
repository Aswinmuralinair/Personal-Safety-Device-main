import os
from werkzeug.utils import secure_filename

ALLOWED_EXT = set(['jpg','jpeg','png','h264','mp4','json', 'wav', 'txt'])

def allowed_filename(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXT

def save_file_safe(file_storage, out_dir):
    if not file_storage or not file_storage.filename or not allowed_filename(file_storage.filename):
        return None
    
    name = secure_filename(file_storage.filename)
    path = os.path.join(out_dir, name)
    file_storage.save(path)
    return path