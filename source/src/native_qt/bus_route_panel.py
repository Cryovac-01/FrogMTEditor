"""
Bus Route Configurator panel for the Frog Mod Editor.

Provides an interactive map view of Jeju Island with bus stop markers,
route visualization, estimated payout calculation, and route export
in the game's JSON format (with GUIDs for each bus stop).

The map uses a real satellite/terrain image from the game, rendered as
a background in a QPainter-based widget.
"""
from __future__ import annotations

import json
import math
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

import economy_editor as eco
from i18n import _ as _t

# ---------------------------------------------------------------------------
# Map image path – resolved relative to this file's directory
# ---------------------------------------------------------------------------
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "assets")
_MAP_IMAGE_PATH = os.path.join(_ASSETS_DIR, "jeju_map_dark.png")


# ---------------------------------------------------------------------------
# Colour tokens
# ---------------------------------------------------------------------------
_BG = "#161c26"
_SURFACE = "#1c2533"
_CARD = "#212c3d"
_BORDER = "#2d3948"
_TEXT = "#edf2f7"
_MUTED = "#8b97a8"
_ACCENT = "#67bfd9"
_ROUTE_COLOR = "#f2c94c"
_STOP_COLOR = "#6fcf97"
_STOP_SELECTED = "#67bfd9"
_WATER = "#0f1820"
_LAND = "#1a2636"
_ROAD = "#2d3948"

# ---------------------------------------------------------------------------
# Bus stop data with in-game GUIDs
# Coordinates are in game coordinate range [0-4096] x [0-4096].
# The game map has THREE main areas:
#   - Northern Island (game_y > 3100): Jeju City, airport, Hallim, etc.
#   - Mid Zone (game_y 2200-3100): Industrial areas
#   - Southern Island (game_y < 2200): Seoguipo, Gangjung, industrial, etc.
# GUIDs extracted from Jeju_World.uexp (binary asset analysis).
# ---------------------------------------------------------------------------
BUS_STOPS: List[Dict[str, Any]] = [
    # =====================================================================
    # NORTH ISLAND (game_y > 3100)
    # =====================================================================
    {"id": "Gimnyeong-Beach", "name": "Gimnyeong Beach", "x": 2693, "y": 3874, "region": "North",
     "guid": "C3D9DF934E94644EC9A2C59F14D4F345"},
    {"id": "Jeju_Harbor", "name": "Jeju Harbor", "x": 2346, "y": 3867, "region": "North",
     "guid": None},
    {"id": "Overseas_Imports_Co.", "name": "Overseas Imports Co.", "x": 1663, "y": 3315, "region": "North",
     "guid": "E7C60E614FFE12DB6E043EBF2C963985"},
    {"id": "Gujwa_HeavyDutyShop", "name": "Gujwa Heavy Duty Shop", "x": 2790, "y": 3850, "region": "North",
     "guid": "1BEFB4AE446296EC3555089B21F19787"},
    {"id": "Gujwa_FoodFactory", "name": "Gujwa Food Factory", "x": 2805, "y": 3840, "region": "North",
     "guid": "7B85AA344D7BA8D8A3DE3D8C8C37B94F"},
    {"id": "Gujwa_ToyFactory", "name": "Gujwa Toy Factory", "x": 2798, "y": 3830, "region": "North",
     "guid": "200728FF4B6D9EDE7B3085AE369D0AD4"},
    {"id": "IldoApt", "name": "Ildo Apartment", "x": 2280, "y": 3770, "region": "North",
     "guid": "F885CE5C4807C9641551DAA106D92E4E"},
    {"id": "Jeju_Airport_1F", "name": "Jeju Airport 1F", "x": 2225, "y": 3770, "region": "North",
     "guid": "BAC3997B4FA75DF7682249882F153E73"},
    {"id": "Jeju_Airport_3F", "name": "Jeju Airport 3F", "x": 2235, "y": 3770, "region": "North",
     "guid": "E305C6C94089253771F7618E21609129"},
    {"id": "DoNamApt", "name": "Donam Apartment", "x": 2241, "y": 3768, "region": "North",
     "guid": "35202D644A02714B557B3EB56E5B80ED"},
    {"id": "Jeju_Airport", "name": "Jeju Airport", "x": 2230, "y": 3765, "region": "North",
     "guid": None},
    {"id": "Sangdo-Farm", "name": "Sangdo Farm", "x": 2878, "y": 3763, "region": "North",
     "guid": "F8258C2F430359489B352280504AB02A"},
    {"id": "IreneApt", "name": "Irene Apartment", "x": 2275, "y": 3760, "region": "North",
     "guid": "E8CD092642EE44A296E86F83CF5DD1D1"},
    {"id": "Jeju_BurgerShop", "name": "Jeju BurgerShop", "x": 2290, "y": 3758, "region": "North",
     "guid": "E17BBC6444C6F938630841A8D02546E2"},
    {"id": "JejuOfficeDistrict", "name": "Jeju Office District", "x": 2325, "y": 3755, "region": "North",
     "guid": "120562D445446FCB0876EE849ACC0BB6"},
    {"id": "Sangdo-Sawmill", "name": "Sangdo Sawmill", "x": 2885, "y": 3755, "region": "North",
     "guid": "F6E68416486F5660E48FDE9ACB15544E"},
    {"id": "HanSolApt", "name": "Hansol Apartment", "x": 2260, "y": 3752, "region": "North",
     "guid": "C4EB2CCF46081C3EE32419BF4D7A9A45"},
    {"id": "Jeju_Hospital", "name": "Jeju Hospital", "x": 2335, "y": 3750, "region": "North",
     "guid": "9F6CC6A04785500708B5D6BCD1A0F1C5"},
    {"id": "JejuBusTerminal", "name": "Jeju Bus Terminal", "x": 2302, "y": 3745, "region": "North",
     "guid": "6BD14DE047E0A4491BEA0692A2ED9263"},
    {"id": "Jeju_Supermarket", "name": "Jeju Supermarket", "x": 2315, "y": 3735, "region": "North",
     "guid": "A7248FB447519F0027BEAB99F3BFEDD3"},
    {"id": "Oedo", "name": "Oedo", "x": 2117, "y": 3727, "region": "North",
     "guid": "C270F0D64664C4CBC47974AF2AAE0F3F"},
    {"id": "Seong-San_Highschool", "name": "Seongsan Highschool", "x": 2980, "y": 3660, "region": "North",
     "guid": "4196A142444C2EE79A88639836B5542E"},
    {"id": "Seong-San_BusTerminal", "name": "Seongsan Bus Terminal", "x": 2985, "y": 3654, "region": "North",
     "guid": "C4BDDC2B4F1BB33A3FC3AA8B0CA663DD"},
    {"id": "ConcreteFactory", "name": "Concrete Factory", "x": 2480, "y": 3650, "region": "North",
     "guid": "7565FC294FAECC23D62091BE9DED3F3F"},
    {"id": "Seong-San_Village", "name": "Seongsan Village", "x": 2990, "y": 3648, "region": "North",
     "guid": "2551D8954B74C8F0DB77EAB70B920CD3"},
    {"id": "Jocheon_Old_Mansion", "name": "Jocheon Old Mansion", "x": 2576, "y": 3677, "region": "North",
     "guid": None},
    {"id": "Ae-Wol_Warehouse", "name": "Aewol Warehouse", "x": 1926, "y": 3669, "region": "North",
     "guid": "3CD4C9504D6012A8A22855A12B614D56"},
    {"id": "Ae-wol_FurnitureStore", "name": "Aewol FurnitureStore", "x": 1970, "y": 3638, "region": "North",
     "guid": "5BDE6261497D60683ED56E8FC979B680"},
    {"id": "Military_Base", "name": "Military Base", "x": 2268, "y": 3630, "region": "North",
     "guid": "B437256F437EA0CAE12301B29437F3D1"},
    {"id": "Military_Base_Entrance", "name": "Military Base Entrance", "x": 2280, "y": 3620, "region": "North",
     "guid": "C8F88BDA4486E4DDB65E8F9B3E153892"},
    {"id": "East-Dealership", "name": "East Dealership", "x": 2950, "y": 3600, "region": "North",
     "guid": "8AFF9CB7469F89B2E40BD2896771F11D"},
    {"id": "DriverLicenseExaminationOffice", "name": "Driver License Office", "x": 2340, "y": 3590, "region": "North",
     "guid": "3CD9ED4E4EA24B4C186C698355B26E9F"},
    {"id": "Hallim_BusTerminal", "name": "Hallim Bus Terminal", "x": 1624, "y": 3588, "region": "North",
     "guid": "ED02CFDA4A5C5F64EE2F1AAFB32DE445"},
    {"id": "Water-Factory", "name": "Water Factory", "x": 2380, "y": 3500, "region": "North",
     "guid": "3ECD3D3A4999CCF61727E0990A1F8BB2"},
    {"id": "Hallim_Fishing_Village", "name": "Hallim Fishing Village", "x": 1767, "y": 3498, "region": "North",
     "guid": "C1F6A70246B42C0035FFBB9F6B50CC56"},
    {"id": "Modern-Dealership", "name": "Modern Dealership", "x": 2395, "y": 3480, "region": "North",
     "guid": "B67EBB8443C85EF20D0453AC4574735F"},
    {"id": "Iseungag", "name": "Iseungag", "x": 2440, "y": 3442, "region": "North",
     "guid": None},
    {"id": "1100-RestArea", "name": "1100 Rest Area", "x": 2200, "y": 3400, "region": "North",
     "guid": "A570B06340B88E8C55FAF5B82A9CB8E6"},
    {"id": "An-Deok_Bank", "name": "Andeok Bank", "x": 1900, "y": 3400, "region": "North",
     "guid": "BB2F43EB42BED3498AE922B0E2ED2672"},
    {"id": "Sin-Chang_Warehouse", "name": "Sinchang Warehouse", "x": 1674, "y": 3394, "region": "North",
     "guid": "297A784E42BE26B6A54CF7BA4A9337AA"},
    {"id": "Santas_Cabin", "name": "Santa's Cabin", "x": 2231, "y": 3379, "region": "North",
     "guid": None},
    {"id": "CastleRanch", "name": "Castle Ranch", "x": 1690, "y": 3360, "region": "North",
     "guid": "FBB53F4A4DB4E021E33843B67C1EAA6C"},
    {"id": "Pyo-Seon", "name": "Pyoseon Fishing Village", "x": 2865, "y": 3352, "region": "North",
     "guid": "3DF8DA01482A930E29EC55AE2EB76876"},
    {"id": "Tosan_Trailer_Dealership", "name": "Trailer Dealership", "x": 2704, "y": 3349, "region": "North",
     "guid": "026CBC254A59A7DFE775E495DCE000FD"},
    {"id": "Noksan_Ranch", "name": "Noksan Ranch", "x": 1700, "y": 3350, "region": "North",
     "guid": "6798938542E6420D2F5828A4134E368F"},
    {"id": "Noksan_FuelSupply", "name": "Noksan Fuel Supply", "x": 1710, "y": 3340, "region": "North",
     "guid": "17965E124A15AD85DF641E98955806B0"},
    {"id": "Power_Plant", "name": "Power Plant", "x": 1849, "y": 3326, "region": "North",
     "guid": "DC3380FA4795A147CE1A2CA581CCD5C7"},
    {"id": "Dae-Jeong", "name": "Daejeong", "x": 1660, "y": 3320, "region": "North",
     "guid": "1F4ED02941A79D07C331CF830143C747"},
    {"id": "Gang-Jung_East", "name": "Gangjung East", "x": 2303, "y": 3312, "region": "North",
     "guid": None},
    {"id": "TowTruck_Dealership", "name": "Tow Truck Dealership", "x": 1680, "y": 3310, "region": "North",
     "guid": "B2D545E94F1F4667FC14C3BFFC4F64E9"},
    {"id": "Truck_Dealership", "name": "Truck Dealership", "x": 1666, "y": 3307, "region": "North",
     "guid": "2974204C458B3B9943CB6280C0531DD9"},
    {"id": "Gosan_Truck", "name": "Gosan Truck Stop", "x": 1666, "y": 3307, "region": "North",
     "guid": None},
    {"id": "Namwon-Corn-Farm", "name": "Namwon Corn Farm", "x": 2554, "y": 3294, "region": "North",
     "guid": "9DFFE7C5481E0320CC682FBEC7344EBE"},
    {"id": "Junkyard", "name": "Junkyard", "x": 2034, "y": 3258, "region": "North",
     "guid": "93B5867E4AC019E5F92835B960C7CDC4"},
    {"id": "Seo-Gui-Po_CityHall", "name": "Seoguipo City Hall", "x": 2373, "y": 3228, "region": "North",
     "guid": "4600F0824B31A4FC9DB16BA8CD3387D6"},
    {"id": "Seoguipo_DownTown", "name": "Seoguipo DownTown", "x": 2373, "y": 3228, "region": "North",
     "guid": None},
    {"id": "Seo-Gui-Po_Office_District_1", "name": "Seoguipo Office District 1", "x": 2383, "y": 3238, "region": "North",
     "guid": None},
    {"id": "Seo-Gui-Po_Office_District_2", "name": "Seoguipo Office District 2", "x": 2388, "y": 3233, "region": "North",
     "guid": "820A93A94EFFFE5D23A617A0CAFD0FA1"},
    {"id": "Seo-Gui-Po_Office_District_3", "name": "Seoguipo Office District 3", "x": 2393, "y": 3225, "region": "North",
     "guid": "755E218542D3C5742D0D26AC6FBE54F5"},
    {"id": "Jung-Mun", "name": "Jungmun", "x": 2320, "y": 3220, "region": "North",
     "guid": "1F8E6487485365AE9715D78E4AACB763"},
    {"id": "Gang-Jung_Church", "name": "Gangjung Church", "x": 2265, "y": 3220, "region": "North",
     "guid": "78250EDF4694F89C1867869801E657CA"},
    {"id": "Seo-Gui-Po_Furniture_Factory", "name": "Seoguipo Furniture Factory", "x": 2363, "y": 3218, "region": "North",
     "guid": "B9849A7F41F1C740BDCC1B8BB20E25B2"},
    {"id": "Seo-Gui-Po_Hospital", "name": "Seoguipo Hospital", "x": 2405, "y": 3235, "region": "North",
     "guid": "823D19B24BBEB289D544CCB492DFFCB1"},
    {"id": "Seo-Gui-Po_PoliceStation", "name": "Seoguipo Police Station", "x": 2398, "y": 3215, "region": "North",
     "guid": "4CD94D8745C5D73A45E04193C72C0408"},
    {"id": "Gangjung_West", "name": "Gangjung West", "x": 2240, "y": 3215, "region": "North",
     "guid": None},
    {"id": "Gang-Jung_Terminal", "name": "Gangjung Terminal", "x": 2255, "y": 3210, "region": "North",
     "guid": "A65E6E4647093938401CD2965BB6BCBA"},
    {"id": "Seo-Gui-Po_Mansion", "name": "Seoguipo Mansion", "x": 2383, "y": 3210, "region": "North",
     "guid": "00714A0000DF2A000053BE000072CD00"},
    {"id": "Seo-Gui-Po_Dream_APT", "name": "Seoguipo Dream APT", "x": 2378, "y": 3222, "region": "North",
     "guid": "6B9946944451444003007BA500000001"},
    {"id": "Gang-Jung_Supermarket", "name": "Gangjung Supermarket", "x": 2268, "y": 3200, "region": "North",
     "guid": "33C6C2A74F29A86F3D86999A1CCEE813"},
    {"id": "Gang-Jung_Warehouse", "name": "Gangjung Warehouse", "x": 2245, "y": 3200, "region": "North",
     "guid": "8E361AE7458077635500589EAD4DFD75"},
    {"id": "Gang-Jung_Sashimi", "name": "Gangjung Sashimi", "x": 2260, "y": 3205, "region": "North",
     "guid": "58D4029F4467DF3C003F6C8B7BCE9CE3"},
    {"id": "Gang-Jung_Hardware", "name": "Gangjung Hardware", "x": 2248, "y": 3195, "region": "North",
     "guid": None},
    {"id": "Gang-Jung_Harbor", "name": "Gangjung Harbor", "x": 2235, "y": 3190, "region": "North",
     "guid": "0A5E838D478C9D4E27E06F9052447A6A"},

    # =====================================================================
    # MID ZONE (game_y 2200-3100)
    # =====================================================================
    {"id": "Logging-Area", "name": "Logging Area", "x": 1750, "y": 3100, "region": "Mid",
     "guid": "025247064BCCD322731A778051620E2A"},
    {"id": "Ansan-Speedway", "name": "Ansan Speedway", "x": 1913, "y": 2881, "region": "Mid",
     "guid": "91A987D94BCD5051286669B80F661760"},
    {"id": "Biyang_Warehouse", "name": "Biyang Warehouse", "x": 2649, "y": 2859, "region": "Mid",
     "guid": "979D01BE47CEF4E2800B0A8EAF8ACCC7"},
    {"id": "Hupo_Factory", "name": "Hupo Factory", "x": 2875, "y": 2841, "region": "Mid",
     "guid": None},
    {"id": "Migeum_Warehouse", "name": "Migeum Warehouse", "x": 2854, "y": 2569, "region": "Mid",
     "guid": "01FEA01C4671AA9C7474D8A711F11C68"},
    {"id": "Nobong", "name": "Nobong", "x": 1995, "y": 2513, "region": "Mid",
     "guid": None},
    {"id": "Nobong_Landfill", "name": "Nobong Landfill", "x": 1956, "y": 2474, "region": "Mid",
     "guid": "8A32A36E46A18990722E31A4C00E6AE4"},
    {"id": "Ga-Pa_Ranch", "name": "Gapa Ranch", "x": 2528, "y": 2355, "region": "Mid",
     "guid": "03CD66E64AD693BFEDBE10BBA250666B"},
    {"id": "Dongsan", "name": "Dongsan", "x": 1564, "y": 2327, "region": "Mid",
     "guid": None},
    {"id": "Ga-Pa_Supermarket", "name": "Gapa Supermarket", "x": 2540, "y": 2320, "region": "Mid",
     "guid": "6EA57E764C5E5E1B5CAB0C9B227116C3"},
    {"id": "Ga-Pa_Farm", "name": "Gapa Farm", "x": 2534, "y": 2308, "region": "Mid",
     "guid": "6B1A095E4F10ADE1C9E7E6AA70959FF6"},

    # =====================================================================
    # SOUTH ISLAND (game_y < 2200)
    # =====================================================================
    {"id": "Gwangjin_CoalMine", "name": "Gwangjin Coal Mine", "x": 2948, "y": 2116, "region": "South",
     "guid": "6B53797B4940CED7C55478AB78DF51EF"},
    {"id": "Gwangjin_Village", "name": "Gwangjin Village", "x": 2905, "y": 1867, "region": "South",
     "guid": "FD6E88F74B261362C447F7942909B63B"},
    {"id": "Namdang_Sawmill", "name": "Namdang Sawmill", "x": 2663, "y": 1847, "region": "South",
     "guid": "07D6A47D411BD427587F4D8A96F974D8"},
    {"id": "Baram_Farm", "name": "Baram Farm", "x": 1417, "y": 1603, "region": "South",
     "guid": None},
    {"id": "Yeongil_DrillingPlant", "name": "Yeongil Drilling Plant", "x": 1991, "y": 1603, "region": "South",
     "guid": "B50868704B424D0E514A4EB1ED040D16"},
    {"id": "Dragstrip", "name": "Dragstrip", "x": 3111, "y": 1413, "region": "South",
     "guid": None},
    {"id": "Ara_Secondary", "name": "Ara Secondary", "x": 2910, "y": 1338, "region": "South",
     "guid": None},
    {"id": "Dasa_Harbor", "name": "Dasa Harbor", "x": 910, "y": 1277, "region": "South",
     "guid": "B2BF65C543DE6BCD47A4409590A3C809"},
    {"id": "Daejin", "name": "Daejin", "x": 3162, "y": 1193, "region": "South",
     "guid": None},
    {"id": "Joil_GasStation", "name": "Joil Gas Station", "x": 2072, "y": 1055, "region": "South",
     "guid": "512BF73E4FB6D7658C1000AD36D4262E"},
    {"id": "Ara_Terminal", "name": "Ara Terminal", "x": 3034, "y": 923, "region": "South",
     "guid": None},
    {"id": "Sanho_OilRefinery", "name": "Sanho Oil Refinery", "x": 964, "y": 748, "region": "South",
     "guid": "3E2458204E251E35373275BDC6E2EB4B"},
    {"id": "Machajin_Factory", "name": "Machajin Factory", "x": 1797, "y": 562, "region": "South",
     "guid": None},
]

# Predefined game routes (stop sequences)
GAME_ROUTES: List[Dict[str, Any]] = [
    {
        "name": "Gang-Jung Town 1",
        "stops": [
            "Gang-Jung_Terminal", "Jung-Mun", "Gang-Jung_Harbor",
            "Gang-Jung_Supermarket", "Gang-Jung_Sashimi",
            "Gang-Jung_Warehouse", "Gang-Jung_Church",
            "Gang-Jung_Terminal", "Gang-Jung_Church",
            "Gang-Jung_Warehouse", "Gang-Jung_Harbor", "Jung-Mun",
        ],
    },
    {
        "name": "Jeju to Gang-Jung",
        "stops": [
            "Gang-Jung_Terminal", "JejuBusTerminal",
        ],
    },
    {
        "name": "Jeju-1",
        "stops": [
            "JejuBusTerminal", "Jeju_Airport_1F", "Oedo",
            "JejuOfficeDistrict", "IldoApt", "Jeju_Harbor",
            "JejuBusTerminal", "Jeju_Harbor", "IldoApt",
            "JejuOfficeDistrict", "Oedo", "Jeju_Airport_3F",
            "Jeju_Airport_1F",
        ],
    },
    {
        "name": "Jeju-2",
        "stops": [
            "JejuBusTerminal", "IldoApt", "Military_Base_Entrance",
            "Military_Base", "Jeju_Hospital", "Jeju_Supermarket",
            "IldoApt",
        ],
    },
    {
        "name": "Olle Ring",
        "stops": [
            "Gang-Jung_Terminal", "Gang-Jung_Warehouse",
            "Seo-Gui-Po_PoliceStation", "Modern-Dealership",
            "Namwon-Corn-Farm", "Pyo-Seon", "ConcreteFactory",
            "Seong-San_Village", "Seong-San_BusTerminal",
            "Gujwa_HeavyDutyShop", "Gimnyeong-Beach",
            "TowTruck_Dealership", "East-Dealership",
            "JejuBusTerminal", "Jeju_Airport_3F",
            "Ae-wol_FurnitureStore", "Ae-Wol_Warehouse",
            "Hallim_BusTerminal", "Sin-Chang_Warehouse",
            "Truck_Dealership", "Overseas_Imports_Co.",
            "Dae-Jeong", "An-Deok_Bank", "Junkyard",
            "Gang-Jung_Supermarket",
        ],
    },
    {
        "name": "Seo-Gui-Po Downtown",
        "stops": [
            "Gang-Jung_Terminal", "Seo-Gui-Po_PoliceStation",
            "Seo-Gui-Po_CityHall", "Seo-Gui-Po_Dream_APT",
            "Seo-Gui-Po_Office_District_2", "Seo-Gui-Po_Office_District_3",
            "Seo-Gui-Po_Office_District_3", "Seo-Gui-Po_Hospital",
            "Seo-Gui-Po_Office_District_2", "Seo-Gui-Po_Furniture_Factory",
            "Seo-Gui-Po_Office_District_2", "Seo-Gui-Po_Dream_APT",
            "Seo-Gui-Po_PoliceStation",
        ],
    },
    {
        "name": "Sung-San HighSchool 1",
        "stops": [
            "Gang-Jung_Terminal", "Seo-Gui-Po_PoliceStation",
            "Seo-Gui-Po_CityHall", "Pyo-Seon",
            "Seong-San_Village", "Seong-San_Highschool",
            "Pyo-Seon", "Modern-Dealership",
            "Seo-Gui-Po_PoliceStation", "Gang-Jung_Warehouse",
        ],
    },
    {
        "name": "West-1",
        "stops": [
            "Gang-Jung_Terminal", "Junkyard", "An-Deok_Bank",
            "Dae-Jeong", "Overseas_Imports_Co.", "Truck_Dealership",
            "Sin-Chang_Warehouse", "Hallim_BusTerminal",
            "Ae-Wol_Warehouse", "Ae-wol_FurnitureStore",
            "Jeju_Airport_1F", "Jeju_Airport_3F",
            "JejuOfficeDistrict", "DriverLicenseExaminationOffice",
            "CastleRanch", "An-Deok_Bank", "Junkyard",
            "Jung-Mun", "Gang-Jung_Harbor",
        ],
    },
]

# Stop lookup
_STOP_MAP: Dict[str, Dict[str, Any]] = {s["id"]: s for s in BUS_STOPS}


def _label(text: str, kind: str = "body") -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setWordWrap(True)
    if kind == "title":
        lbl.setStyleSheet(f"color: {_TEXT}; font-size: 16px; font-weight: 600;")
    elif kind == "section":
        lbl.setStyleSheet(f"color: {_TEXT}; font-size: 13px; font-weight: 600;")
    elif kind == "muted":
        lbl.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
    elif kind == "eyebrow":
        lbl.setStyleSheet(f"color: {_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
    elif kind == "accent":
        lbl.setStyleSheet(f"color: {_ACCENT}; font-size: 13px; font-weight: 600;")
    elif kind == "success":
        lbl.setStyleSheet(f"color: {_SUCCESS}; font-size: 12px; font-weight: 600;")
    elif kind == "warning":
        lbl.setStyleSheet(f"color: {_ROUTE_COLOR}; font-size: 12px;")
    else:
        lbl.setStyleSheet(f"color: {_TEXT}; font-size: 13px;")
    return lbl


def _action_button(text: str, role: str = "primary") -> QtWidgets.QPushButton:
    btn = QtWidgets.QPushButton(text)
    if role == "primary":
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT};
                color: #0b1410;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #7dcce4;
            }}
        """)
    elif role == "success":
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {_STOP_COLOR};
                color: #0b1410;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #8fdfaa;
            }}
        """)
    else:
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {_BORDER};
            }}
        """)
    return btn


def _distance(s1: Dict, s2: Dict) -> float:
    """Euclidean distance between two stops in map units."""
    dx = s1["x"] - s2["x"]
    dy = s1["y"] - s2["y"]
    return math.sqrt(dx * dx + dy * dy)


def estimate_route_payout(
    stop_ids: List[str],
    bus_base: float = 120.0,
    bus_per_100m: float = 3.6,
    bus_multiplier: float = 1.0,
    avg_passengers: int = 5,
) -> Dict[str, Any]:
    """Estimate payout for a bus route.

    Uses game coordinate distances scaled to approximate in-game meters.
    Game coordinate units are roughly 1 meter (map is ~4km across).
    """
    if len(stop_ids) < 2:
        return {"total_distance": 0, "estimated_payment": 0, "stops": 0}

    total_dist = 0.0
    for i in range(len(stop_ids) - 1):
        s1 = _STOP_MAP.get(stop_ids[i])
        s2 = _STOP_MAP.get(stop_ids[i + 1])
        if s1 and s2:
            total_dist += _distance(s1, s2)

    # Convert game units to approximate game meters
    game_meters = total_dist * 1.0
    # Payment formula: passengers x (base + per_100m x distance/100)
    per_stop_payment = bus_base + bus_per_100m * (game_meters / 100.0)
    total_payment = avg_passengers * per_stop_payment * bus_multiplier

    return {
        "total_distance_map": total_dist,
        "total_distance_meters": game_meters,
        "estimated_payment": total_payment,
        "per_stop_payment": per_stop_payment * bus_multiplier,
        "stops": len(stop_ids),
        "avg_passengers": avg_passengers,
    }


def generate_route_guid() -> str:
    """Generate a new random GUID in the Motor Town hex format (32 uppercase hex chars)."""
    return uuid.uuid4().hex.upper()


def export_route_json(route_name: str, stop_ids: List[str], route_guid: str = None) -> str:
    """Generate route JSON in Motor Town's import format.

    Format:
        {
            "guid": "<32-char hex>",
            "routeName": "<name>",
            "points": [
                {"pointGuid": "<bus stop guid>", "routeFlags": 0},
                ...
            ]
        }

    Stops without a known GUID are included with a placeholder comment.
    """
    if route_guid is None:
        route_guid = generate_route_guid()

    points = []
    for sid in stop_ids:
        stop = _STOP_MAP.get(sid)
        if stop:
            guid = stop.get("guid")
            if guid:
                points.append({"pointGuid": guid, "routeFlags": 0})
            else:
                # Stop exists but GUID not extracted - use placeholder
                points.append({"pointGuid": f"UNKNOWN_GUID_{sid}", "routeFlags": 0})

    route_data = {
        "guid": route_guid,
        "routeName": route_name,
        "points": points,
    }
    return json.dumps(route_data, indent=4)


# ---------------------------------------------------------------------------
# Map Widget (QPainter-based)
# ---------------------------------------------------------------------------
class JejuMapWidget(QtWidgets.QWidget):
    """Interactive map widget showing bus stops and routes on Jeju Island.

    Supports zoom (mouse wheel or the three overlay buttons) and pan
    (middle-click drag, or Shift + left-click drag). Keyboard shortcuts:
    + zoom in, - zoom out, 0 reset view.
    """

    stop_clicked = QtCore.Signal(str)  # emits stop ID when clicked

    # Zoom limits — 1.0 = full island fits the widget, 10.0 = tight closeup.
    ZOOM_MIN = 1.0
    ZOOM_MAX = 10.0
    # Multiplicative factor per wheel tick (1.2 ≈ 20% per notch).
    ZOOM_STEP = 1.2
    _MARGIN = 20

    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(600, 450)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._route_stops: List[str] = []
        self._hover_stop: Optional[str] = None
        self._selected_stops: set = set()

        # View state — user zoom (1.0 = fit) and the game-space coord the
        # widget centers on. Pan is represented by moving view_center, not
        # by an offset, so zoom-at-cursor math stays trivially invertible.
        self._user_zoom: float = 1.0
        self._view_center: QtCore.QPointF = QtCore.QPointF(2048.0, 2048.0)

        # Pan-drag state
        self._panning: bool = False
        self._pan_last: QtCore.QPointF = QtCore.QPointF()

        # Load the real map image
        self._map_pixmap: Optional[QtGui.QPixmap] = None
        if os.path.isfile(_MAP_IMAGE_PATH):
            self._map_pixmap = QtGui.QPixmap(_MAP_IMAGE_PATH)
        else:
            # Fallback: try path relative to CWD
            alt = os.path.join("source", "assets", "jeju_map_dark.png")
            if os.path.isfile(alt):
                self._map_pixmap = QtGui.QPixmap(alt)

        # Overlay zoom controls (top-right corner, repositioned on resize).
        # Icons are vector-drawn via QPainter rather than unicode glyphs
        # so they render identically regardless of system-font coverage
        # (U+2212 MINUS and U+2302 HOUSE aren't in every Windows font).
        self._zoom_in_btn = self._make_overlay_button(
            'zoom_in', _t("Zoom in (mouse wheel up)"))
        self._zoom_out_btn = self._make_overlay_button(
            'zoom_out', _t("Zoom out (mouse wheel down)"))
        self._zoom_reset_btn = self._make_overlay_button(
            'fit', _t("Fit to view (keyboard: 0)"))
        self._zoom_in_btn.clicked.connect(lambda: self._zoom_around_center(self.ZOOM_STEP))
        self._zoom_out_btn.clicked.connect(lambda: self._zoom_around_center(1.0 / self.ZOOM_STEP))
        self._zoom_reset_btn.clicked.connect(self.reset_view)

    # ------------------------------------------------------------------
    # Public view controls
    # ------------------------------------------------------------------
    def set_route(self, stop_ids: List[str]) -> None:
        self._route_stops = stop_ids
        self._selected_stops = set(stop_ids)
        self.update()

    def clear_route(self) -> None:
        self._route_stops = []
        self._selected_stops = set()
        self.update()

    def reset_view(self) -> None:
        """Restore zoom=1, centered on the map."""
        self._user_zoom = 1.0
        self._view_center = QtCore.QPointF(2048.0, 2048.0)
        self.update()

    # ------------------------------------------------------------------
    # Overlay controls
    # ------------------------------------------------------------------
    def _make_overlay_button(self, role: str, tooltip: str) -> QtWidgets.QPushButton:
        btn = QtWidgets.QPushButton(self)
        btn.setToolTip(tooltip)
        btn.setFixedSize(28, 28)
        btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        # Draw the icon ourselves so we don't depend on any particular
        # font shipping a given codepoint. 18px glyph inside a 28px button.
        btn.setIcon(self._render_overlay_icon(role, 18))
        btn.setIconSize(QtCore.QSize(18, 18))
        btn.setStyleSheet(
            "QPushButton {"
            " background: rgba(20, 30, 40, 0.85);"
            f" border: 1px solid {_BORDER};"
            " border-radius: 4px; }"
            "QPushButton:hover { background: rgba(40, 60, 80, 0.95); }"
            "QPushButton:pressed { background: rgba(80, 120, 160, 0.95); }"
        )
        return btn

    @staticmethod
    def _render_overlay_icon(role: str, size: int) -> QtGui.QIcon:
        """Vector-draw a zoom-in (plus), zoom-out (minus), or fit-to-view
        (square with inward corners) icon. Font-independent, so the
        buttons never render as blank glyph-fallback squares."""
        pix = QtGui.QPixmap(size, size)
        pix.fill(QtCore.Qt.GlobalColor.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor(_TEXT))
        pen.setWidthF(2.0)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        c = size / 2.0
        arm = size * 0.30   # distance from center to each end of the cross

        if role == 'zoom_in':
            p.drawLine(QtCore.QPointF(c - arm, c), QtCore.QPointF(c + arm, c))
            p.drawLine(QtCore.QPointF(c, c - arm), QtCore.QPointF(c, c + arm))
        elif role == 'zoom_out':
            p.drawLine(QtCore.QPointF(c - arm, c), QtCore.QPointF(c + arm, c))
        elif role == 'fit':
            # Outer square representing the view frame, with four small
            # inward-pointing corner ticks (classic "fit to view" icon).
            m = size * 0.18
            r = QtCore.QRectF(m, m, size - 2 * m, size - 2 * m)
            p.drawRect(r)
            tick = size * 0.10
            # Top-left corner tick pointing inward
            p.drawLine(QtCore.QPointF(r.left(), r.top() + tick),
                       QtCore.QPointF(r.left() + tick, r.top()))
            # Top-right
            p.drawLine(QtCore.QPointF(r.right(), r.top() + tick),
                       QtCore.QPointF(r.right() - tick, r.top()))
            # Bottom-left
            p.drawLine(QtCore.QPointF(r.left(), r.bottom() - tick),
                       QtCore.QPointF(r.left() + tick, r.bottom()))
            # Bottom-right
            p.drawLine(QtCore.QPointF(r.right(), r.bottom() - tick),
                       QtCore.QPointF(r.right() - tick, r.bottom()))
        p.end()
        return QtGui.QIcon(pix)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        # Stack overlay zoom buttons vertically in the top-right corner.
        pad = 8
        bw = self._zoom_in_btn.width()
        bh = self._zoom_in_btn.height()
        x = self.width() - pad - bw
        y = pad
        self._zoom_in_btn.move(x, y)
        y += bh + 4
        self._zoom_out_btn.move(x, y)
        y += bh + 4
        self._zoom_reset_btn.move(x, y)

    # ------------------------------------------------------------------
    # Coordinate transforms
    # ------------------------------------------------------------------
    def _fit_scale(self) -> float:
        """Pixel-per-game-unit at zoom=1 — whole 4096x4096 map fits the widget."""
        w = self.width()
        h = self.height()
        sx = (w - 2 * self._MARGIN) / 4096.0
        sy = (h - 2 * self._MARGIN) / 4096.0
        return max(0.0001, min(sx, sy))

    def _effective_scale(self) -> float:
        return self._fit_scale() * self._user_zoom

    def _map_to_widget(self, mx: float, my: float) -> QtCore.QPointF:
        """Convert game coords (0-4096) to widget pixel coords. Y is inverted."""
        scale = self._effective_scale()
        dx_game = mx - self._view_center.x()
        dy_game = my - self._view_center.y()
        return QtCore.QPointF(
            self.width() / 2 + dx_game * scale,
            self.height() / 2 - dy_game * scale,  # y flipped
        )

    def _widget_to_map(self, wx: float, wy: float) -> Tuple[float, float]:
        scale = self._effective_scale()
        dx_pix = wx - self.width() / 2
        dy_pix = wy - self.height() / 2
        return (
            self._view_center.x() + dx_pix / scale,
            self._view_center.y() - dy_pix / scale,
        )

    # ------------------------------------------------------------------
    # Zoom / pan math
    # ------------------------------------------------------------------
    def _zoom_at(self, new_zoom: float, anchor: QtCore.QPointF) -> None:
        """Set zoom such that the game coord currently under `anchor`
        (widget-space pixel point) stays under `anchor` after the zoom."""
        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, new_zoom))
        if abs(new_zoom - self._user_zoom) < 1e-6:
            return
        # Game-space point that should stay fixed under the anchor pixel.
        anchor_game_x, anchor_game_y = self._widget_to_map(anchor.x(), anchor.y())
        self._user_zoom = new_zoom
        # Solve for the new view_center that keeps anchor_game under the anchor pixel.
        new_scale = self._effective_scale()
        dx_pix = anchor.x() - self.width() / 2
        dy_pix = anchor.y() - self.height() / 2
        self._view_center = QtCore.QPointF(
            anchor_game_x - dx_pix / new_scale,
            anchor_game_y + dy_pix / new_scale,
        )
        self._clamp_view_center()
        self.update()

    def _zoom_around_center(self, factor: float) -> None:
        center = QtCore.QPointF(self.width() / 2, self.height() / 2)
        self._zoom_at(self._user_zoom * factor, center)

    def _clamp_view_center(self) -> None:
        """Keep the view center inside the game-space rectangle so the
        user can't pan the map completely off-screen."""
        x = max(0.0, min(4096.0, self._view_center.x()))
        y = max(0.0, min(4096.0, self._view_center.y()))
        self._view_center = QtCore.QPointF(x, y)

    # ------------------------------------------------------------------
    # Input events
    # ------------------------------------------------------------------
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = self.ZOOM_STEP if delta > 0 else 1.0 / self.ZOOM_STEP
        self._zoom_at(self._user_zoom * factor, QtCore.QPointF(event.position()))
        event.accept()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        k = event.key()
        if k in (QtCore.Qt.Key.Key_Plus, QtCore.Qt.Key.Key_Equal):
            self._zoom_around_center(self.ZOOM_STEP)
            event.accept()
            return
        if k in (QtCore.Qt.Key.Key_Minus, QtCore.Qt.Key.Key_Underscore):
            self._zoom_around_center(1.0 / self.ZOOM_STEP)
            event.accept()
            return
        if k == QtCore.Qt.Key.Key_0:
            self.reset_view()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)

        # Background (ocean)
        p.fillRect(self.rect(), QtGui.QColor(_WATER))

        if self._map_pixmap and not self._map_pixmap.isNull():
            # Image covers full game space [0, 4096] x [0, 4096]
            img_tl = self._map_to_widget(0, 4096)    # game top-left (0, 4096)
            img_br = self._map_to_widget(4096, 0)     # game bottom-right (4096, 0)
            target_rect = QtCore.QRectF(img_tl, img_br)
            p.drawPixmap(target_rect.toRect(), self._map_pixmap)
        else:
            # Fallback: draw simple land shapes if image not available
            p.setBrush(QtGui.QColor(_LAND))
            p.setPen(QtGui.QPen(QtGui.QColor(_BORDER), 1.5))
            north_pts = [
                (310, 40), (450, 48), (600, 60), (750, 95), (880, 190),
                (850, 270), (600, 260), (350, 255), (220, 190), (240, 100),
            ]
            p.drawPolygon(QtGui.QPolygonF([self._map_to_widget(x, y) for x, y in north_pts]))
            south_pts = [
                (30, 320), (300, 300), (600, 340), (900, 460), (980, 620),
                (920, 800), (700, 935), (400, 955), (100, 830), (40, 600),
            ]
            p.drawPolygon(QtGui.QPolygonF([self._map_to_widget(x, y) for x, y in south_pts]))

        # Draw route lines
        if len(self._route_stops) >= 2:
            route_pen = QtGui.QPen(QtGui.QColor(_ROUTE_COLOR), 3, QtCore.Qt.PenStyle.SolidLine)
            route_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            p.setPen(route_pen)
            for i in range(len(self._route_stops) - 1):
                s1 = _STOP_MAP.get(self._route_stops[i])
                s2 = _STOP_MAP.get(self._route_stops[i + 1])
                if s1 and s2:
                    p1 = self._map_to_widget(s1["x"], s1["y"])
                    p2 = self._map_to_widget(s2["x"], s2["y"])
                    p.drawLine(p1, p2)

            # Draw route order numbers
            font = p.font()
            font.setPointSize(8)
            font.setBold(True)
            p.setFont(font)
            for idx, stop_id in enumerate(self._route_stops):
                stop = _STOP_MAP.get(stop_id)
                if stop:
                    pt = self._map_to_widget(stop["x"], stop["y"])
                    p.setPen(QtCore.Qt.PenStyle.NoPen)
                    p.setBrush(QtGui.QColor(_ROUTE_COLOR))
                    p.drawEllipse(pt, 10, 10)
                    p.setPen(QtGui.QColor("#0b1410"))
                    p.drawText(
                        QtCore.QRectF(pt.x() - 10, pt.y() - 10, 20, 20),
                        QtCore.Qt.AlignmentFlag.AlignCenter,
                        str(idx + 1),
                    )

        # Draw all stops
        for stop in BUS_STOPS:
            pt = self._map_to_widget(stop["x"], stop["y"])
            is_selected = stop["id"] in self._selected_stops
            is_hover = stop["id"] == self._hover_stop

            if is_selected:
                color = QtGui.QColor(_STOP_SELECTED)
                radius = 7
            elif is_hover:
                color = QtGui.QColor(_TEXT)
                radius = 6
            else:
                color = QtGui.QColor(_STOP_COLOR)
                radius = 4

            # Dim stops without GUIDs slightly
            if not stop.get("guid") and not is_selected and not is_hover:
                color = QtGui.QColor("#4a6060")

            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(pt, radius, radius)

            # Draw label for selected or hovered stops
            if is_selected or is_hover:
                font = p.font()
                font.setPointSize(8)
                font.setBold(is_selected)
                p.setFont(font)
                p.setPen(QtGui.QColor(_TEXT))
                label_text = stop["name"]
                if not stop.get("guid"):
                    label_text += " (no GUID)"
                label_rect = QtCore.QRectF(pt.x() + 10, pt.y() - 8, 200, 16)
                p.drawText(label_rect, QtCore.Qt.AlignmentFlag.AlignLeft, label_text)

        # Draw legend
        self._draw_legend(p)
        p.end()

    def _draw_legend(self, p: QtGui.QPainter) -> None:
        x, y = 10, self.height() - 110
        font = p.font()
        font.setPointSize(9)
        p.setFont(font)

        items = [
            (_STOP_COLOR, _t("Bus Stop")),
            (_STOP_SELECTED, _t("On Route")),
            (_ROUTE_COLOR, _t("Route Path")),
            ("#4a6060", _t("No GUID (cannot export)")),
        ]
        for color, label in items:
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(color))
            p.drawEllipse(QtCore.QPointF(x + 6, y + 6), 5, 5)
            p.setPen(QtGui.QColor(_MUTED))
            p.drawText(x + 16, y + 11, label)
            y += 20

        # Zoom readout + navigation hint.
        p.setPen(QtGui.QColor(_MUTED))
        p.drawText(x, y + 11, _t("Zoom: {zoom:.1f}\u00d7  \u2014  wheel zooms, middle-click or Shift+drag pans, 0 resets").format(zoom=self._user_zoom))

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        # If a pan-drag is in progress, translate view_center by the
        # game-space equivalent of the mouse delta and skip hover logic.
        if self._panning:
            pos = QtCore.QPointF(event.position())
            delta = pos - self._pan_last
            scale = self._effective_scale()
            if scale > 0:
                self._view_center = QtCore.QPointF(
                    self._view_center.x() - delta.x() / scale,
                    self._view_center.y() + delta.y() / scale,  # y flipped
                )
                self._clamp_view_center()
            self._pan_last = pos
            self.update()
            return

        # Hover detection — hit radius scales down with zoom so the
        # catch zone stays constant in on-screen pixels.
        mx, my = self._widget_to_map(event.position().x(), event.position().y())
        hit_radius = 80.0 / max(1.0, self._user_zoom)
        closest = None
        closest_dist = hit_radius
        for stop in BUS_STOPS:
            d = math.sqrt((stop["x"] - mx) ** 2 + (stop["y"] - my) ** 2)
            if d < closest_dist:
                closest_dist = d
                closest = stop["id"]

        if closest != self._hover_stop:
            self._hover_stop = closest
            self.setCursor(
                QtCore.Qt.CursorShape.PointingHandCursor if closest
                else QtCore.Qt.CursorShape.ArrowCursor
            )
            self.update()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        # Middle-click or Shift+left-click starts a pan-drag.
        is_shift_left = (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and bool(event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier)
        )
        if event.button() == QtCore.Qt.MouseButton.MiddleButton or is_shift_left:
            self._panning = True
            self._pan_last = QtCore.QPointF(event.position())
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        # Normal left-click selects the hovered stop.
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._hover_stop:
            self.stop_clicked.emit(self._hover_stop)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._panning and event.button() in (
            QtCore.Qt.MouseButton.MiddleButton,
            QtCore.Qt.MouseButton.LeftButton,
        ):
            self._panning = False
            self.setCursor(
                QtCore.Qt.CursorShape.PointingHandCursor if self._hover_stop
                else QtCore.Qt.CursorShape.ArrowCursor
            )
            event.accept()


# ---------------------------------------------------------------------------
# Route Configurator Panel
# ---------------------------------------------------------------------------
class BusRouteConfigPanel(QtWidgets.QWidget):
    """Full bus route configurator with map, stop list, payout estimation, and export."""

    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        super().__init__(parent)
        self._custom_route: List[str] = []
        self._route_guid: str = generate_route_guid()
        self._build_ui()
        self._load_game_routes()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background: {_BG};")
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # -- Left panel: controls ------------------------------------------
        left = QtWidgets.QFrame()
        left.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        left.setMinimumWidth(280)
        left.setMaximumWidth(340)

        left_scroll = QtWidgets.QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        left_scroll.setStyleSheet(f"background: {_SURFACE}; border: none;")

        left_inner = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_inner)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(10)

        left_layout.addWidget(_label(_t("BUS ROUTE CONFIGURATOR"), "eyebrow"))
        left_layout.addWidget(_label(_t("Route Planner"), "title"))
        left_layout.addWidget(_label(
            _t("Select a predefined route or build a custom route by clicking stops on the map. "
            "Export routes as JSON for use with the game's route import system."),
            "muted",
        ))

        # Route selector
        left_layout.addWidget(_label(_t("PREDEFINED ROUTES"), "eyebrow"))
        self.route_combo = QtWidgets.QComboBox()
        self.route_combo.setStyleSheet(f"""
            QComboBox {{
                background: {_CARD};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 13px;
            }}
            QComboBox QAbstractItemView {{
                background: {_CARD};
                color: {_TEXT};
                border: 1px solid {_BORDER};
            }}
        """)
        self.route_combo.addItem(_t("\u2014 Custom Route \u2014"))
        self.route_combo.currentIndexChanged.connect(self._on_route_selected)
        left_layout.addWidget(self.route_combo)

        # Route name input
        left_layout.addWidget(_label(_t("ROUTE NAME"), "eyebrow"))
        self.route_name_input = QtWidgets.QLineEdit()
        self.route_name_input.setPlaceholderText(_t("Enter route name (e.g. Jeju)"))
        self.route_name_input.setText(_t("Custom Route"))
        self.route_name_input.setStyleSheet(f"""
            QLineEdit {{
                background: {_CARD};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {_ACCENT};
            }}
        """)
        left_layout.addWidget(self.route_name_input)

        # Passenger count
        left_layout.addWidget(_label(_t("AVERAGE PASSENGERS"), "eyebrow"))
        self.passenger_spin = QtWidgets.QSpinBox()
        self.passenger_spin.setRange(1, 50)
        self.passenger_spin.setValue(5)
        self.passenger_spin.setStyleSheet(f"""
            QSpinBox {{
                background: {_CARD};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 13px;
            }}
        """)
        self.passenger_spin.valueChanged.connect(self._update_estimate)
        left_layout.addWidget(self.passenger_spin)

        # Current route stops list
        left_layout.addWidget(_label(_t("ROUTE STOPS"), "eyebrow"))
        self.stop_list = QtWidgets.QListWidget()
        self.stop_list.setStyleSheet(f"""
            QListWidget {{
                background: {_CARD};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                font-size: 12px;
            }}
            QListWidget::item {{
                padding: 4px 8px;
            }}
            QListWidget::item:selected {{
                background: {_ACCENT};
                color: #0b1410;
            }}
        """)
        self.stop_list.setMinimumHeight(100)
        left_layout.addWidget(self.stop_list, 1)

        # Route actions (clear / remove)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        self.clear_btn = _action_button(_t("Clear Route"), "secondary")
        self.clear_btn.clicked.connect(self._on_clear_route)
        self.remove_btn = _action_button(_t("Remove Last"), "secondary")
        self.remove_btn.clicked.connect(self._on_remove_last)
        btn_row.addWidget(self.clear_btn)
        btn_row.addWidget(self.remove_btn)
        left_layout.addLayout(btn_row)

        # -- Payout Estimation Card ----------------------------------------
        payout_card = QtWidgets.QFrame()
        payout_card.setStyleSheet(f"""
            QFrame {{
                background: {_CARD};
                border: 1px solid {_BORDER};
                border-radius: 6px;
            }}
        """)
        payout_layout = QtWidgets.QVBoxLayout(payout_card)
        payout_layout.setContentsMargins(12, 12, 12, 12)
        payout_layout.setSpacing(6)
        payout_layout.addWidget(_label(_t("ESTIMATED PAYOUT"), "eyebrow"))
        self.payout_label = _label(_t("$0"), "accent")
        self.payout_label.setStyleSheet(f"color: {_ACCENT}; font-size: 24px; font-weight: 700;")
        payout_layout.addWidget(self.payout_label)
        self.payout_details = _label(_t("Select stops to see estimate"), "muted")
        payout_layout.addWidget(self.payout_details)
        left_layout.addWidget(payout_card)

        # -- Export Card ---------------------------------------------------
        export_card = QtWidgets.QFrame()
        export_card.setStyleSheet(f"""
            QFrame {{
                background: {_CARD};
                border: 1px solid {_BORDER};
                border-radius: 6px;
            }}
        """)
        export_layout = QtWidgets.QVBoxLayout(export_card)
        export_layout.setContentsMargins(12, 12, 12, 12)
        export_layout.setSpacing(8)
        export_layout.addWidget(_label(_t("ROUTE EXPORT"), "eyebrow"))
        export_layout.addWidget(_label(
            _t("Export route as JSON for the game's route import. "
            "Stops without a known GUID will be marked."),
            "muted",
        ))

        export_btn_row = QtWidgets.QHBoxLayout()
        export_btn_row.setSpacing(8)
        self.copy_btn = _action_button(_t("Copy to Clipboard"), "primary")
        self.copy_btn.clicked.connect(self._on_copy_to_clipboard)
        self.save_btn = _action_button(_t("Save as .txt"), "success")
        self.save_btn.clicked.connect(self._on_save_as_txt)
        export_btn_row.addWidget(self.copy_btn)
        export_btn_row.addWidget(self.save_btn)
        export_layout.addLayout(export_btn_row)

        self.export_status = _label("", "muted")
        export_layout.addWidget(self.export_status)
        left_layout.addWidget(export_card)

        left_scroll.setWidget(left_inner)

        left_container = QtWidgets.QVBoxLayout(left)
        left_container.setContentsMargins(0, 0, 0, 0)
        left_container.addWidget(left_scroll)

        root.addWidget(left, 0)

        # -- Right panel: map ----------------------------------------------
        map_frame = QtWidgets.QFrame()
        map_frame.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        map_layout = QtWidgets.QVBoxLayout(map_frame)
        map_layout.setContentsMargins(8, 8, 8, 8)
        map_layout.setSpacing(4)

        map_header = QtWidgets.QHBoxLayout()
        map_header.addWidget(_label(_t("JEJU ISLAND \u2014 MOTOR TOWN MAP"), "eyebrow"))
        map_header.addStretch(1)
        guid_count = sum(1 for s in BUS_STOPS if s.get("guid"))
        self.stop_count_label = _label(
            _t("{count} bus stops ({guid_count} with GUIDs)").format(count=len(BUS_STOPS), guid_count=guid_count), "muted"
        )
        map_header.addWidget(self.stop_count_label)
        map_layout.addLayout(map_header)

        self.map_widget = JejuMapWidget()
        self.map_widget.stop_clicked.connect(self._on_stop_clicked)
        map_layout.addWidget(self.map_widget, 1)

        root.addWidget(map_frame, 1)

    def _load_game_routes(self) -> None:
        for route in GAME_ROUTES:
            self.route_combo.addItem(route["name"])

    def _on_route_selected(self, index: int) -> None:
        if index == 0:
            # Custom route mode
            self._custom_route = []
            self._route_guid = generate_route_guid()
            self.route_name_input.setText(_t("Custom Route"))
            self.map_widget.clear_route()
            self.stop_list.clear()
            self._update_estimate()
            return

        route = GAME_ROUTES[index - 1]
        self._custom_route = list(route["stops"])
        self._route_guid = generate_route_guid()
        self.route_name_input.setText(route["name"])
        self._refresh_route_display()

    def _on_stop_clicked(self, stop_id: str) -> None:
        # Switch to custom mode if a predefined route was selected
        if self.route_combo.currentIndex() != 0:
            self.route_combo.blockSignals(True)
            self.route_combo.setCurrentIndex(0)
            self.route_combo.blockSignals(False)

        if stop_id in self._custom_route:
            self._custom_route.remove(stop_id)
        else:
            self._custom_route.append(stop_id)

        self._refresh_route_display()

    def _on_clear_route(self) -> None:
        self._custom_route = []
        self._route_guid = generate_route_guid()
        self.route_combo.setCurrentIndex(0)
        self._refresh_route_display()

    def _on_remove_last(self) -> None:
        if self._custom_route:
            self._custom_route.pop()
            self._refresh_route_display()

    def _refresh_route_display(self) -> None:
        self.map_widget.set_route(self._custom_route)
        self.stop_list.clear()
        for i, sid in enumerate(self._custom_route):
            stop = _STOP_MAP.get(sid, {})
            name = stop.get("name", sid)
            has_guid = bool(stop.get("guid"))
            suffix = "" if has_guid else " [no GUID]"
            self.stop_list.addItem(f"{i + 1}. {name}{suffix}")
        self._update_estimate()
        self.export_status.setText("")

    def _update_estimate(self) -> None:
        # Get current economy settings
        settings = eco.load_economy_settings()
        bus_label = settings.get('bus_multiplier', '1x (Vanilla)')
        bus_mult = eco.MULTIPLIER_PRESETS.get(bus_label, 1.0)
        if bus_mult is None:
            bus_mult = 1.0  # Custom mode fallback for estimation

        # Get vanilla INI values for bus payment
        vanilla_ini = eco.load_vanilla_balance_ini()
        bus_base = vanilla_ini.get('BusPayment', 120.0)
        bus_per_100m = vanilla_ini.get('BusPaymentPer100Meter', 3.6)

        est = estimate_route_payout(
            self._custom_route,
            bus_base=float(bus_base),
            bus_per_100m=float(bus_per_100m),
            bus_multiplier=bus_mult,
            avg_passengers=self.passenger_spin.value(),
        )

        if est["stops"] < 2:
            self.payout_label.setText(_t("$0"))
            self.payout_details.setText(_t("Add at least 2 stops to see estimate"))
            return

        payment = est["estimated_payment"]
        self.payout_label.setText(f"${payment:,.0f}")
        self.payout_details.setText(
            _t("{stops} stops | ~{distance}m total | ${per_stop}/stop | {passengers} passengers | Bus \u00d7{mult:.0f}").format(
                stops=est['stops'],
                distance=int(est['total_distance_meters']),
                per_stop=int(est['per_stop_payment']),
                passengers=est['avg_passengers'],
                mult=bus_mult
            )
        )

    # ------------------------------------------------------------------
    # Export functionality
    # ------------------------------------------------------------------
    def _get_route_json(self) -> Optional[str]:
        """Generate route JSON, or None if route is empty."""
        if len(self._custom_route) < 2:
            self.export_status.setText(_t("Need at least 2 stops to export."))
            self.export_status.setStyleSheet(f"color: #e74c3c; font-size: 12px;")
            return None

        route_name = self.route_name_input.text().strip() or _t("Custom Route")

        # Warn about stops without GUIDs
        missing_guid = []
        for sid in self._custom_route:
            stop = _STOP_MAP.get(sid)
            if stop and not stop.get("guid"):
                missing_guid.append(stop.get("name", sid))

        json_str = export_route_json(route_name, self._custom_route, self._route_guid)

        if missing_guid:
            names = ", ".join(missing_guid)
            self.export_status.setText(
                _t("Warning: {count} stop(s) missing GUIDs: {names}").format(count=len(missing_guid), names=names)
            )
            self.export_status.setStyleSheet(f"color: {_ROUTE_COLOR}; font-size: 11px;")
        return json_str

    def _on_copy_to_clipboard(self) -> None:
        """Copy route JSON to system clipboard."""
        json_str = self._get_route_json()
        if json_str is None:
            return

        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(json_str)

        missing = any(not _STOP_MAP.get(sid, {}).get("guid") for sid in self._custom_route)
        if not missing:
            self.export_status.setText(_t("Route JSON copied to clipboard!"))
            self.export_status.setStyleSheet(f"color: {_STOP_COLOR}; font-size: 12px; font-weight: 600;")

    def _on_save_as_txt(self) -> None:
        """Save route JSON to a .txt file with a file picker dialog."""
        json_str = self._get_route_json()
        if json_str is None:
            return

        route_name = self.route_name_input.text().strip() or _t("Custom Route")
        default_name = route_name.replace(" ", "_") + "_route.txt"

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            _t("Save Route as TXT"),
            default_name,
            _t("Text Files (*.txt);;JSON Files (*.json);;All Files (*)"),
        )

        if not file_path:
            return  # User cancelled

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(json_str)

            self.export_status.setText(_t("Saved to: {path}").format(path=file_path))
            self.export_status.setStyleSheet(f"color: {_STOP_COLOR}; font-size: 12px; font-weight: 600;")
        except OSError as e:
            self.export_status.setText(_t("Error saving: {error}").format(error=str(e)))
            self.export_status.setStyleSheet(f"color: #e74c3c; font-size: 12px;")
