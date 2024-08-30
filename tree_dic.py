import ujson


def tree_path(tree_dic, org_uuid):
    path = []
    current_uuid = org_uuid  # 获取当前需要的uuid
    while current_uuid:  # 当org_uuid存在
        org_info = tree_dic[current_uuid]  # 获取uuid的中文名称和父级uuid
        if not org_info:
            break
        path.append(org_info["fullname"])
        current_uuid = org_info["parentuuid"]
    return " -> ".join(reversed(path))


if __name__ == '__main__':
    tree_dic = {
        "ORG_29B50": {"fullname": "拱墅区", "parentuuid": ""},
        "ORG_21C02": {"fullname": "党委机构", "parentuuid": "ORG_29B50"},
        "ORG_F1B0D": {"fullname": "拱墅区委领导", "parentuuid": "ORG_21C02"},
        "ORG_6F88D": {"fullname": "拱墅区委办公室", "parentuuid": "ORG_21C02"},
        "ORG_F895B4": {"fullname": "办领导", "parentuuid": "ORG_6F88D"},

    }
    org_uuid = "ORG_6F88D"
    full_path = tree_path(tree_dic, org_uuid)
    print(full_path)
