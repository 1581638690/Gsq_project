key_value = ["page","11"]
strss = "=".join(key_value)
print(strss)
stream={}


def par_value_match(url,parameters):

    stream['gjxz']={"预警主题类型":{"":"全部","0":"企业","1":"事件","2":"人员"},"反馈状态":{"":"全部","0":"未反馈","1":"已反馈"}}
    list_yj = []
    par_lst = parameters.split("&")
    for par in par_lst:
        key, value = par.split("=")
        if key == "page":

            if len(value)>1:

                page_num = int(value[:-1]) + 1
                list_yj.append(f"{key}={page_num}")

        elif key == "yjxxWarningType":
            values_dic = stream["gjxz"].get("预警主题类型")
            values = values_dic.get(value)
            strs = key + "=" + values
            list_yj.append(strs)
        elif  key == "yjxxFeedbackStatus":
            values_dic = stream["gjxz"].get("反馈状态")
            values = values_dic.get(value)
            strs =  key + "=" + values
            list_yj.append(strs)
        else:
            list_yj.append(par)
    return "&".join(list_yj)

if __name__ == '__main__':
    url= ""
    parameters = "page=12&pageSize=10&yjxxWarningType=&yjxxFeedbackStatus="
    res = par_value_match(url, parameters)
    print(res)