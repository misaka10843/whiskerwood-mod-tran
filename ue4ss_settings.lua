local function text(parameter)
    local value = parameter:get()
    if type(value) == "string" then return value end
    return value:ToString()
end

local function translate(_, _, id, title, _, _, description)
    local ok, err = pcall(function()
        local option = text(id)
        local setting = translations[option]
        if not setting then return end
        if setting.name then title:set(FString(setting.name)) end
        if setting.description then description:set(FString(setting.description)) end
        print("[WhiskerwoodTranslator] translated " .. option .. ": " .. text(title) .. "\n")
    end)
    if not ok then print("[WhiskerwoodTranslator] option hook error: " .. tostring(err) .. "\n") end
end

local registered = false
local choice_labels = {
    Off = "关闭", On = "开启", Hide = "隐藏", Show = "显示",
    Fast = "快速", Normal = "普通", ["Very fast"] = "极速",
    ["Thought and Approval"] = "心情与认同度", ["Thought only"] = "仅心情",
    ["No schooling"] = "未受教育", ["1 in 4 Apprentices"] = "约四分之一为学徒",
    ["Fresh Copper"] = "新铜", ["With Patina"] = "铜绿",
    Overflow = "可超出", Capped = "上限内", Both = "两者",
}
local recorded_choices = {}
local function translate_choice(widget, label)
    local ok, err = pcall(function()
        local object = widget:get()
        local path = object:GetFullName():lower()
        if not path:find("settingselector", 1, true) or not path:match("[%.:]selectedoptiontext$") then return end
        local value = text(label)
        local replacement = choice_labels[value]
        if not replacement then return end
        label:set(FText(replacement))
        if not recorded_choices[value] then
            recorded_choices[value] = true
            print("[WhiskerwoodTranslator] display value " .. value .. ": " .. text(label) .. "\n")
        end
    end)
    if not ok then print("[WhiskerwoodTranslator] display hook error: " .. tostring(err) .. "\n") end
end

local function register_choices()
    for _, path in ipairs({"/Script/SystemCore.LocTextBlock:SetText", "/Script/UMG.TextBlock:SetText"}) do
        if StaticFindObject(path):IsValid() then
            RegisterHook(path, translate_choice)
            print("[WhiskerwoodTranslator] display hook active: " .. path .. "\n")
        end
    end
end

local function register()
    if registered then return end
    for _, module in ipairs({"ProjectArco", "SystemCore"}) do
        local path = "/Script/" .. module .. ".ModAPI:RegisterModOptions"
        local func = StaticFindObject(path)
        if func:IsValid() then
            local ok, err = pcall(RegisterHook, path, translate)
            if ok then
                registered = true
                print("[WhiskerwoodTranslator] setting hook active: " .. path .. "\n")
                local choices_ok, choices_err = pcall(register_choices)
                if not choices_ok then print("[WhiskerwoodTranslator] cannot register display hook: "
                    .. tostring(choices_err) .. "\n") end
                return
            end
            print("[WhiskerwoodTranslator] cannot register setting hook: " .. tostring(err) .. "\n")
        end
    end
end

register()
if not registered and RegisterInitGameStatePreHook then
    RegisterInitGameStatePreHook(function()
        register()
        if not registered then print("[WhiskerwoodTranslator] RegisterModOptions not found\n") end
    end)
end
