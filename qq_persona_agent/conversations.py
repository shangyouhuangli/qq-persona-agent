"""Stable conversation keys isolate private IDs from equal numeric group IDs.

Existing SQLite group_id columns carry conversation keys for compatibility.
"""
def private_key(user_id):
    value = str(user_id).strip()
    if not value.isdigit() or int(value) <= 0:
        raise ValueError('请输入有效的数字 QQ 号')
    return 'private:' + value


def is_private(key):
    return str(key).startswith('private:')


def valid_key(key):
    value = str(key)
    return value.isdigit() and int(value) > 0 or is_private(value) and value[8:].isdigit() and int(value[8:]) > 0


async def history(client, key, cursor=None, count=100):
    if is_private(key):
        return await client.get_friend_msg_history(key[8:], cursor, count)
    return await client.get_group_msg_history(key, cursor, count)
