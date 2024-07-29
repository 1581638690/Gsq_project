def par_str_json(parameter):
    data_dic = {}
    if isinstance(parameter, str) and parameter:
        result = parameter.split("&")
        for i in result:
            i_lst = i.split("=")
            if len(i_lst) >1:
                key = i_lst[0]
                value = i_lst[1]
                try:
                    if is_json_string(value):
                        value = json.loads(value)
                except:
                    pass
                data_dic[key] = value
            elif len(i_lst) == 1:
                data_dic[i_lst[0]] = ""
    return data_dic
if __name__ == '__main__':
    parameter = "page=1&size=10&attributeLevel=1"
    data_dic = par_str_json(parameter)
    print(data_dic)

    # 新增表结构
    #df =load ckh by ckh with alter table api_monitor add columns parameter_json String