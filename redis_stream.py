import redis


def conn():
    # 导入配置信息
    r = redis.Redis(host="127.0.0.1", port=16379, password="4d7d4f6ef5d627f43a65d9b4b2ccc875")
    return r


def query_list_http(r, list_name):
    # 检查链接是否成功
    try:
        r.ping()
        print("Connecting to Redis")
    except:
        print("Failed to connect to Redis")
    # 获取整个列表信息
    list_values = r.lrange(list_name, 0, -1)

    # 筛选出包含http的值信息
    http_values = [v.decode() for v in list_values if b"http" in v]
    return http_values


if __name__ == '__main__':
    r = conn()
    http_values = query_list_http(r, "csr-10188025")
    print(http_values)
