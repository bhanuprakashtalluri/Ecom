from itsdangerous import URLSafeSerializer
from keys import secret_key,salt
salt='extra@123'
secret_key='codegnan@123'

def entoken(data):
    serializer=URLSafeSerializer(secret_key)
    return serializer.dumps(data,salt=salt)
def dctoken(data):
    serializer=URLSafeSerializer(secret_key)
    return serializer.loads(data,salt=salt)