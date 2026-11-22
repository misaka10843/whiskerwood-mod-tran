"""Option IDs and labels verified against the Steam Workshop packages."""

OPTIONS = {
    "NoSupportBeams": ("NoSupportBeams_", "No Support Beams - ", "隐藏支撑：", {
        "MinePillars": ("Mine Pillars", "矿井立柱", "隐藏地下的垂直顶板支撑。"),
        "MineRetainers": ("Mine Retainers", "矿井挡撑", "隐藏地形的水平支撑。"),
        "Ladders": ("Ladders", "梯子", "隐藏矿井梯子。"),
        "Buildings": ("Height Supports", "高架支撑", "隐藏所有高架支撑。"),
        "Archways": ("Archways / Stairs / Docks", "拱门／楼梯／码头", "隐藏部分支撑。需重新载入。"),
        "FancyScaffolds": ("Fancy Scaffolds", "精致脚手架", "隐藏精致装饰 Mod 的脚手架。需重新载入地图。"),
        "Pipes": ("Pipes", "管道", "隐藏所有管道支撑。"),
        "Docks": ("Trade Dock", "贸易码头", "隐藏贸易码头的支撑。需重新载入。"),
        "Farms": ("Farms", "农场", "隐藏农场立柱。需重新载入地图。"),
    }),
    "NoPollution": ("NoPollution_", "No Pollution - ", "无污染：", {
        "Smog": ("Visuals", "视觉效果", "隐藏污染视觉效果，不影响玩法。"),
        "Penalties": ("Penalties", "污染惩罚", "返回主菜单后生效。"),
    }),
    "BigStorage": ("BigStorage_", "Big Storage - ", "大容量仓储：", {
        key: (key, title, "返回主菜单后生效。") for key, title in
        (("Shed", "储物棚"), ("Small", "小型仓库"), ("Medium", "中型仓库"),
         ("Central", "中央仓库"), ("Large", "大型仓库"), ("Giant", "巨型仓库"))
    }),
    "HeaterDefaults": ("HeaterDefaults_", "Heaters - ", "取暖设备：", {
        "TurnOnAt": ("default Turn on at (C)", "默认启动温度（°C）",
                     "将仍使用游戏默认值（10°C）的篝火、取暖炉和蒸汽暖气设为此温度。手动调整过的设备不受影响。"),
    }),
    "FastBelts": ("FastBelts_", "Fast Belts: ", "高速传送带：", {
        "Horizontal": ("Horizontal (incl. corners)", "水平传送带（含转角）", "平直传送带及转角可按 2 倍或 10 倍速度运送物品。"),
        "Slide": ("Slide", "滑道", "加快滑道上的物品运送速度。"),
        "Lift": ("Lift", "升降带", "加快垂直升降带上的物品运送速度。"),
        "CLift": ("Curved Lift", "弯曲升降带", "加快弯曲升降带上的物品运送速度。"),
        "CLiftTall": ("Tall Curved Lift", "高弯曲升降带", "加快高弯曲升降带上的物品运送速度。"),
        "Sorter": ("Sorter", "分拣器", "加快分拣器的物品运送速度。"),
        "Splitter": ("Splitter", "分流器", "加快分流器的物品运送速度。"),
        "InBox": ("In-Box", "传送带入口", "加快传送带入口的物品运送速度。"),
        "Extractor": ("Extractor", "提取器", "加快提取器从仓库取出物品的速度。"),
        "Warehouse": ("Warehouse Intake", "仓库入口", "以 10 倍速度送入仓库，避免高速传送带堵住入口。"),
    }),
    "WhiskerChurch": ("WhiskerChurch_", "", "鼠民教会：", {
        "AltarLimit": ("Altar daily offerings", "祭坛每日供奉上限",
                       "设置每座祭坛每天接受的供奉次数，默认 15 次。达到上限后，祭坛休息到次日，再继续接受所选供品。"),
        "SpiritBlessing": ("Spirit blessing", "神灵祝福",
                           "设置路过祭坛神灵附近的鼠民是否获得好心情，以及是否同时提高认同度。"),
    }),
    "Apartments": ("Apartments_", "", "鼠民公寓：", {
        "Hearth": ("Apartment hearths", "公寓壁炉",
                   "启用后，看火员为公寓壁炉添燃料并给周围供暖。关闭后，公寓不消耗燃料，也不产生热量或烟雾。"),
        "HideUnreachable": ("Hide false Unreachable marker", "隐藏误报的无法到达标记",
                             "隐藏公寓门口误报的「无法到达」标记。"),
    }),
    "LongTails": ("LongTails_", "", "长尾列车：", {
        "CartsPerTrain": ("Carts per train", "每列车的车厢数", "列车会增加到指定的车厢数。请按列车长度建造站台。"),
        "DockSeconds": ("Station stop seconds", "停站时间（秒）",
                        "列车在车站每格停留的秒数。数值越小，停站越短。乘客仍可完成上车。"),
    }),
    "Airships": ("Airships_", "", "飞艇：", {
        "SkyLane": ("Sky lane mode", "空中航线模式", "启用后，铺轨工具会绘制飞艇用的隐形航线。"),
        "Markers": ("Sky lane markers", "航线标记", "开启后，发光标记会显示所有空中航线和飞艇码头。即时生效。"),
        "Speed": ("Airship speed", "飞艇速度", "普通使用列车速度规则。快速为两倍速度且不受坡度影响。极速可在长航线上维持高速。即时生效。"),
    }),
    "TurboBoost": ("TurboBoost_", "Turbo Boost - ", "游戏加速：", {
        "Speed2": ("Speed 2", "速度档 2", "覆盖游戏的两倍速设置。"),
        "Speed3": ("Speed 3", "速度档 3", "覆盖游戏的三倍速设置。"),
    }),
    "FaithfulCopperSlides": ("FaithfulCopperSlides-", "Faithful Copper Slides: ", "铜滑道外观：", {
        "WhiskerSlideMaterial": ("Whisker Slide appearance", "鼠民滑道", "选择鼠民滑道的材质外观。"),
        "ConveyorSlideMaterial": ("Conveyor Down-Drop Slide appearance", "传送带下行滑道", "选择传送带滑道的材质外观。"),
    }),
    "Embassies": ("Embassies_", "", "大使馆：", {
        "Schooling": ("Newcomer schooling", "新移民教育程度",
                      "设置新到的仓鼠和花栗鼠的教育程度。「未受教育」时全部从头学习；「约四分之一为学徒」时，约四分之一会以学徒身份抵达。"),
    }),
    "WarehousesExtended": ("WarehousesExtended_", "Warehouses Extended - ", "扩展仓库：", {
        "Storage": ("Available Storage", "可用仓储空间", ""),
        "Capacity": ("Capacity Count", "容量统计", ""),
        "Settings": ("Copy/Paste Buttons", "复制／粘贴按钮", ""),
        "Keys": ("Hotkeys", "快捷键", "按 Ctrl+C 复制设置，按 Ctrl+V 粘贴。"),
    }),
}


def option_labels(mod):
    id_prefix, english, chinese, options = OPTIONS[mod]
    return {id_prefix + suffix: (english + name, chinese + title, description)
            for suffix, (name, title, description) in options.items()}


DEFAULTS = {option: {"name": title, **({"description": description} if description else {})}
            for mod in OPTIONS for option, (_, title, description) in option_labels(mod).items()}

RUNTIME_KEY = "ue4ss.setting."


def option_key(key):
    option, _, field = key.removeprefix(RUNTIME_KEY).rpartition(".")
    return option, field
