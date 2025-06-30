from ulid import ulid

def generate_short_uuid(n=10):
    u = ulid()
    return str(u)[:n]