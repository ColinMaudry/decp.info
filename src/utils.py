operators = [
    ["s<", "<"],
    ["s>", ">"],
    ["icontains", "contains"],
]


def split_filter_part(filter_part):
    print("filter part", filter_part)
    for operator_group in operators:
        if operator_group[0] in filter_part:
            name_part, value_part = filter_part.split(operator_group[0], 1)
            name_part = name_part.strip()
            value = value_part.strip()
            name = name_part[name_part.find("{") + 1 : name_part.rfind("}")]

            return name, operator_group[1], value

    return [None] * 3
