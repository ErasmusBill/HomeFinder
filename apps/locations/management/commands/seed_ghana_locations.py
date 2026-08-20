import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.locations.models import Region, District, Town, Area
from apps.common.cache import invalidate_locations_cache

logger = logging.getLogger(__name__)

GHANA_LOCATIONS = {
    "Greater Accra": {
        "Accra Metropolitan": {
            "Accra Central": ["Osu", "Ridge", "Adabraka", "Asylum Down", "Victoriaborg", "Tudu", "Ministries", "Makola", "James Town", "Ussher Town"],
            "Cantonments": ["East Cantonments", "Cantonments Central", "Switchback Road", "El-Wak Area"],
            "Airport": ["Airport Residential Area", "Airport Hills", "Airport City", "Airport West", "Manet"],
            "East Legon": ["East Legon Hills", "East Legon Central", "Adjiringanor", "Trassaco Valley", "Bawaleshie", "American House", "Nmai Dzorn"],
            "Dzorwulu": ["Dzorwulu Central", "Dzorwulu Extension", "Airport By-pass"],
            "Roman Ridge": ["Roman Ridge Central", "Roman Ridge North"],
            "Labone": ["Labone South", "Labone North", "Coffee Shop Area"],
            "Abelemkpe": ["Old Abelemkpe", "New Abelemkpe"],
            "Kokomlemle": ["Kokomlemle Commercial", "Kokomlemle Residential", "Mallam Atta"],
        },
        "Ayawaso West Municipal": {
            "Legon": ["University of Ghana Campus", "Legon Botanical Gardens Area", "West Legon / Westlands", "Agric Complex"],
            "Abelenkpe": ["Abelenkpe Central", "Abelenkpe Extension"],
            "Dzorwulu": ["Dzorwulu Junction", "Dzorwulu Station"],
            "Roman Ridge": ["Roman Ridge South"],
            "Bawaleshie": ["Bawaleshie Village", "Shiashie"],
        },
        "Ayawaso East Municipal": {
            "Nima": ["Nima Central", "Nima 441", "Nima Market", "Kanda Highway"],
            "Kanda": ["Kanda Estates", "Kanda 441", "GBC Area"],
        },
        "Ayawaso North Municipal": {
            "Maamobi": ["Maamobi Central", "Maamobi East", "Nima-Maamobi Boundary"],
            "Pig Farm": ["Pig Farm Roundabout", "Pig Farm Main"],
        },
        "Ayawaso Central Municipal": {
            "Kotobabi": ["Kotobabi Down", "Kotobabi Police Station Area", "Alajo"],
            "Alajo": ["Alajo Central", "Alajo North", "Railway Line"],
            "Caprice": ["Caprice Main", "Avenor Border"],
        },
        "Okaikwei North Municipal": {
            "Achimota": ["Achimota Mile 7", "Achimota Forest Area", "Achimota Market", "Abofu", "Christian Village", "Neoplan"],
            "Tesano": ["North Tesano", "South Tesano", "Tesano Police Station Area"],
            "Akweteyman": ["Akweteyman Junction", "Akweteyman Central"],
            "Abeka": ["Abeka Lapaz", "Abeka Market", "Abeka Post Office"],
            "Lapaz": ["Lapaz Main", "Nyamekye", "Fishpond", "Bambolino Area"],
        },
        "Ablekuma North Municipal": {
            "Darkuman": ["Darkuman Junction", "Darkuman Kokompe", "Nyamekye"],
            "Kwashieman": ["Kwashieman Official Town", "Kwashieman Central", "Sakora"],
            "Odorkor": ["Odorkor Official Town", "Odorkor Tipper", "Odorkor Maclean"],
            "Awoshie": ["Awoshie Mangoase", "Awoshie Water Crossing", "Baah Yard", "Last Stop"],
        },
        "Ablekuma Central Municipal": {
            "Mataheko": ["Mataheko Central", "Flamingo", "Mars"],
            "Abossey Okai": ["Abossey Okai Central", "Auto Parts Zone", "SDA Area"],
            "Kaneshie": ["Kaneshie First Light", "Kaneshie Market", "Zongo Junction", "Pamprom"],
            "Laterbiokorshie": ["Laterbiokorshie Main", "Radio Gold Area"],
        },
        "Ablekuma West Municipal": {
            "Dansoman": ["Dansoman Estates", "Sahara", "Control", "Exhibition", "Roundabout", "Agege", "Gbebu", "Akooko Foto", "Seven Days", "Keep Fit"],
            "Mpoase": ["Mpoase Central", "Mpoase Down"],
        },
        "Korle Klottey Municipal": {
            "Osu": ["Oxford Street", "Osu Castle Area", "Ringway Estates", "RE", "Ashante", "Ako Adjei"],
            "Adabraka": ["Overhead", "Roxy", "PTC", "Adabraka Official Town"],
            "Ridge": ["North Ridge", "West Ridge", "Ministries Gate"],
        },
        "La Dade Kotopon Municipal": {
            "La": ["Labadi Beach Area", "Trade Fair Area", "South La", "La Wireless", "Tse Addo", "Burma Camp", "Airport Hills Border"],
            "Cantonments East": ["Akosombo Road", "Prince of Peace Area"],
        },
        "Ledzokuku Municipal": {
            "Teshie": ["Teshie Camp 2", "Teshie First Junction", "Teshie Nungua Estate", "Bush Road", "Fertilizer", "Teshie Tsui Bleoo", "Aboma", "Sango Lagoon"],
        },
        "Krowor Municipal": {
            "Nungua": ["Nungua Barrier", "Nungua Traditional Town", "Nungua Cold Store", "Buade", "Ravico", "Coco Beach", "C社区", "Addogonno"],
        },
        "Adentan Municipal": {
            "Adentan": ["Adentan Housing", "Adentan Village", "Commandos", "SSNIT Flats", "Adenta Barrier", "Frafraha", "Amanfro", "Amrahia", "Ashiyie", "Malejor"],
            "Adjiringanor": ["Adjiringanor North", "School Junction", "Ashaley Botwe", "Ogbojo", "Little Roses"],
            "Ashaley Botwe": ["Botwe Third Gate", "Botwe Old Town", "Lakeside Estate", "Nanakrom"],
        },
        "Ga East Municipal": {
            "Dome": ["Dome Pillar 2", "Dome Crossing", "Dome Market", "Dome CFC"],
            "Taifa": ["Taifa Burkina", "Taifa Junction", "Taifa Bankyease"],
            "Kwabenya": ["Kwabenya Atomic", "Kwabenya Hills", "Kwabenya Musuku", "ACP Junction", "Pokukrom"],
            "Haatso": ["Haatso Supermarket", "Haatso Ecomog", "Yam Market", "Agbogba"],
            "Abokobi": ["Abokobi Central", "Sesemi", "Teiman", "Oyarifa", "Danfa"],
        },
        "Ga West Municipal": {
            "Amasaman": ["Amasaman Central", "Amasaman Stadium Area", "Sarpeiman", "Ardeyman", "Opah"],
            "Pokuase": ["Pokuase Interchange", "Pokuase ACP", "Pokuase Katapor", "Mayera", "Ayawaso"],
            "Kotoku": ["Kotoku Station", "Papaase"],
        },
        "Ga North Municipal": {
            "Ofankor": ["Ofankor Barrier", "Ofankor Roundabout", "Asofan", "Tantra Hill", "Mile 7 Extension"],
            "Achimota North": ["Mile 7", "St. Johns Area"],
        },
        "Ga Central Municipal": {
            "Sowutuom": ["Sowutuom Central", "Sowutuom Last Stop", "Antieku"],
            "Anyaa": ["Anyaa Market", "Anyaa NIC", "Anyaa Last Stop", "School Junction"],
            "Ablekuma": ["Ablekuma Curve", "Ablekuma Fanmilk", "Joma", "Olebu"],
            "Santa Maria": ["Santa Maria Last Stop", "Blue Kiosk", "A-Lang"],
        },
        "Ga South Municipal": {
            "Ngleshie Amanfro": ["Amanfro Top", "Amanfro Peace Town", "American Town"],
            "Kasoa Border": ["Iron City", "Tuba", "Kokrobite", "Bortianor", "Oshiyie", "Langma", "Tsokome", "Aplaku", "Old Barrier"],
            "Weija": ["Weija Dam Site", "Weija Choice", "Tetegu", "Oblogo"],
        },
        "Weija Gbawe Municipal": {
            "Gbawe": ["Gbawe Zero", "Gbawe CP", "Gbawe Bulemin", "Gbawe Top Base", "Gbawe Gonse"],
            "Mallam": ["Mallam Junction", "Mallam Market", "Mallam Atta", "Gbawe Road"],
            "McCarthy Hill": ["Lower McCarthy", "Upper McCarthy", "Mendskrom"],
        },
        "Tema Metropolitan": {
            "Tema Community 1": ["Market Area", "Site 1", "Site 2", "Site 20", "Padmore"],
            "Tema Community 2": ["BBC Area", "Aggrey Road", "Com 2 Market"],
            "Tema Community 3": ["Site A", "Site B", "Vienna City Area"],
            "Tema Community 4": ["Central Hospital Area", "Site 1", "Chemu Park"],
            "Tema Community 5": ["State Hotel Area", "Site A", "Site B"],
            "Tema Community 6": ["Community 6 Shell", "Greenwich Area"],
            "Tema Community 7": ["Post Office Area", "Texpo Border"],
            "Tema Community 8": ["Com 8 Market", "Site A"],
            "Tema Community 9": ["General Hospital Area", "Adjei Kojo Border"],
            "Tema Community 10": ["Affluent Enclave", "Golf Course Area"],
            "Tema Community 11": ["Shell Filling Station Area", "Com 11 Residential"],
            "Tema Community 12": ["Tema Steel Works Area", "Com 12 Annex"],
            "Tema Community 25": ["Com 25 Mall Area", "Devtraco Courts", "Emefs Hillview", "Beverly Hills", "PS Global"],
            "Manhean (Newtown)": ["Tema Newtown", "Bankuman", "Kpehe"],
        },
        "Ashaiman Municipal": {
            "Ashaiman Central": ["Ashaiman Main Market", "Traffic Light", "Official Town", "Lebanon", "Zenu", "Jericho", "Middle East", "Valco Flat", "Taboo Line", "Night Market"],
        },
        "Kpone Katamanso Municipal": {
            "Kpone": ["Kpone Barrier", "Kpone Beach Area", "Bediako"],
            "Katamanso": ["Katamanso Valley", "Kubekro"],
            "Oyibi": ["Oyibi Central", "Valley View University Area", "Saasabi", "Appolonia City"],
        },
        "Shai Osudoku District": {
            "Dodowa": ["Dodowa Forest", "Dodowa Market", "Wedokum", "Asebi", "Ayikuma"],
            "Asutsuare": ["Asutsuare Junction", "Sugar Factory Area"],
        },
        "Ningo Prampram District": {
            "Prampram": ["Prampram Beach Area", "New Jerusalem", "Dawhenya", "Central University Area", "Afienya", "Mataheko Prampram", "Mobole"],
            "Old Ningo": ["Old Ningo Town", "Ahwiam", "Dawa"],
        },
        "Ada East District": {
            "Ada Foah": ["Ada Estuary", "Aqua Safari Area", "Big Ada", "Kasseh Ada", "Totpekope"],
        },
        "Ada West District": {
            "Sege": ["Sege Central", "Anyamam", "Koluedor", "Boi"],
        },
    },
    "Ashanti": {
        "Kumasi Metropolitan": {
            "Kumasi Central": ["Adum", "Kejetia", "Bompata", "Roman Hill", "Asafo", "Fante New Town", "Alabar", "Mbrom", "Amakom"],
            "Nhyiaeso": ["Nhyiaeso Central", "Ahodwo", "Ahodwo Roundabout", "Danyame", "Ridge", "TUC", "South Suntreso", "North Suntreso"],
            "Bantama": ["Bantama High Street", "Komfo Anokye Area", "North Suntreso", "Abrepo Junction", "Bantama Market"],
            "Subin": ["Asafo Roundabout", "Labour", "Asem", "Fadama"],
        },
        "Asokwa Municipal": {
            "Asokwa": ["Asokwa Residential", "Ahinsan", "Ahinsan Estate", "Kaase Industrial", "Chirapatre", "Chirapatre Estate", "Atonsu", "Agogo", "Gyinyase", "Kuwait"],
        },
        "Oforikrom Municipal": {
            "Oforikrom": ["KNUST Campus", "Ayigya", "Ayeduase", "Kotei", "Boadi", "Emena", "Appiadu", "Kokoben", "Anwomaso", "Kentinkrono", "Dichemso"],
        },
        "Kwadaso Municipal": {
            "Kwadaso": ["Kwadaso Estate", "Kwadaso Central", "Tanoso", "Sowutuom", "Nyankyerenease", "Denkyemuoso", "Asuoyeboah", "Edwenase", "Apatrapa"],
        },
        "Suame Municipal": {
            "Suame": ["Suame Magazine", "Suame Roundabout", "Maakro", "Tarkwa Maakro", "Anomangye", "Kronom", "Breman", "Kronum Kwapra"],
        },
        "Old Tafo Municipal": {
            "Tafo": ["Old Tafo", "Tafo Nhyiaeso", "Pankrono", "Pankrono Estate", "Adabraka Tafo"],
        },
        "Asokore Mampong Municipal": {
            "Asokore Mampong": ["Asokore Mampong Palace", "Parkoso", "Aboabo No 1", "Aboabo No 2", "Akorem", "Sawaba", "Asawase", "Dichemso Border"],
        },
        "Ejisu Municipal": {
            "Ejisu": ["Ejisu Central", "Kwaso", "Fumesua", "CSIR Area", "Besease", "Tikrom", "Onwe", "Boankra Inland Port", "Donyina"],
        },
        "Juaben Municipal": {
            "Juaben": ["Juaben Town", "Nobewam", "Dumakwai", "Boamadumase"],
        },
        "Obuasi Municipal": {
            "Obuasi Central": ["Tutuka", "Wawasi", "Gausu", "Anyinam", "Brahabebome", "Estate", "Kunka", "Bediem"],
        },
        "Obuasi East District": {
            "Tutuka East": ["Boete", "Kwabenakwa", "Diawuoso", "Akrokerri Road"],
        },
        "Bekwai Municipal": {
            "Bekwai": ["Bekwai Town", "Anwiankwanta", "Kokofu", "Poano", "Dominase"],
        },
        "Mampong Municipal": {
            "Mampong": ["Mampong Central", "Asante Mampong Town", "Kofiase", "Daaho", "Bunuso"],
        },
        "Asante Akim Central Municipal": {
            "Konongo": ["Konongo Central", "Odumase", "Fankyeneko", "Nyaboe"],
        },
        "Atwima Nwabiagya Municipal": {
            "Nkawie": ["Nkawie Central", "Toase", "Abuakwa", "Sepaase", "Akropong", "Asuofua", "Bareese"],
        },
        "Atwima Kwanwoma District": {
            "Twedie": ["Twedie Central", "Foase", "Kotwi", "Brofoyedru", "Trede", "Ampabame"],
        },
        "Kwabre East Municipal": {
            "Mamponteng": ["Mamponteng Central", "Ahwiaa Wood Village", "Fawoade", "Kenyasi", "Ntonso Kente Village", "Asonomaso"],
        },
        "Afigya Kwabre South District": {
            "Kodie": ["Kodie Central", "Bronkong", "Afrancho", "Buoho", "Tetrem", "Boamang"],
        },
        "Offinso Municipal": {
            "Offinso": ["Offinso New Town", "Dentin", "Abofour", "Amoawi", "Asamankama"],
        },
    },
    "Eastern": {
        "New Juaben South Municipal": {
            "Koforidua": ["Koforidua Central", "Adweso", "Suhyen", "Effiduase", "Asokore", "Two Streams", "Anlo Town", "Betom", "Srodae", "Old Estate", "New Estate", "Akwadum"],
        },
        "New Juaben North Municipal": {
            "Effiduase": ["Effiduase Town", "Asokore Town", "Oyoko", "Jumapo"],
        },
        "Akuapem South Municipal": {
            "Nsawam Border": ["Aburi", "Ahwerase", "Peduase", "Kitase", "Gyankama", "Obodan", "Pokrom"],
        },
        "Akuapem North Municipal": {
            "Akropong": ["Akropong Central", "Mampong Akuapem", "Tutu", "Amanokrom", "Mamfe", "Larteh", "Obosomase"],
        },
        "Nsawam Adoagyiri Municipal": {
            "Nsawam": ["Nsawam Central", "Adoagyiri", "Djankrom", "Dobro", "Chinto", "Otoase"],
        },
        "Suhum Municipal": {
            "Suhum": ["Suhum Town", "Akorabo", "Ondome", "Kraboa Coaltar Road"],
        },
        "Abuakwa South Municipal": {
            "Kyebi": ["Kyebi Town", "Asiakwa", "Apedwa", "Bunso Arboretum Area", "Asafo"],
        },
        "Yilo Krobo Municipal": {
            "Somanya": ["Somanya Central", "Sra", "Oterkpolu", "Klo Agogo"],
        },
        "Lower Manya Krobo Municipal": {
            "Odumase Krobo": ["Odumase Central", "Kpong", "Akuse", "Nuaso", "Agormanya"],
        },
        "Asuogyaman District": {
            "Atimpoku": ["Atimpoku Central", "Akosombo", "Akosombo Hydro Area", "Senchi", "Anum", "Boso"],
        },
        "Birim Central Municipal": {
            "Akim Oda": ["Oda Central", "Oda Nkwanta", "Old Town", "Asuboa"],
        },
        "Kwahu West Municipal": {
            "Nkawkaw": ["Nkawkaw Central", "Adoagyiri Nkawkaw", "Fodome", "Trado"],
        },
        "Kwahu South District": {
            "Mpraeso": ["Mpraeso Central", "Obomeng", "Obo Kwahu", "Atibie", "Nkwatia"],
        },
    },
    "Western": {
        "Sekondi Takoradi Metropolitan": {
            "Takoradi": ["Market Circle", "Beach Road", "Airport Ridge", "Chapel Hill", "Anaji", "Anaji Estate", "Kwesimintsim", "Effiakuma", "Tanokrom", "New Takoradi"],
            "Sekondi": ["Sekondi Central", "Essikado", "Ketan", "Ketan Estates", "Kweikuma", "Kojokrom", "Bakado", "Ekuase"],
        },
        "Effia Kwesimintsim Municipal": {
            "Effia": ["Effia Central", "Effiakuma New Site", "Kwesimintsim Central", "Assakae", "Whindo", "Adientem"],
        },
        "Ahanta West Municipal": {
            "Agona Nkwanta": ["Agona Nkwanta Town", "Busua Beach", "Dixcove", "Princess Town", "Apowa"],
        },
        "Tarkwa Nsuaem Municipal": {
            "Tarkwa": ["Tarkwa Central", "UMaT Area", "Tamso", "Nsuta", "Cyanide", "Akoon", "Brahabobome"],
        },
        "Prestea Huni Valley Municipal": {
            "Bogoso": ["Bogoso Central", "Prestea Town", "Huni Valley", "Aboso"],
        },
        "Nzema East Municipal": {
            "Axim": ["Axim Central", "Fort St Antonio Area", "Brawire", "Apewosika"],
        },
        "Ellembelle District": {
            "Nkroful": ["Nkroful Town", "Esiama", "Kikam", "Aiyinasi", "Atuabo Gas Plant Area"],
        },
    },
    "Central": {
        "Cape Coast Metropolitan": {
            "Cape Coast": ["Cape Coast Central", "UCC Campus Area", "Pedu", "Aboom", "Ola", "Abura Cape Coast", "Kotokuraba", "Amanful", "Adisadel", "Kakumdo", "Brimso", "Ankaful"],
        },
        "Komenda Edina Eguafo Abirem Municipal": {
            "Elmina": ["Elmina Castle Area", "Bantuma", "Komenda Town", "Agona Abrem", "Kissie"],
        },
        "Awutu Senya East Municipal": {
            "Kasoa": ["Kasoa New Market", "Ofaakor", "CP Kasoa", "Opeikuma", "Walantu", "Iron City", "Zongo Kasoa", "Adam Nana", "Akweley", "Millennium City"],
        },
        "Effutu Municipal": {
            "Winneba": ["Winneba Central", "UEW South Campus", "UEW North Campus", "Lowcost", "Gyahadze", "Sankor"],
        },
        "Agona West Municipal": {
            "Agona Swedru": ["Swedru Central", "Mandela", "Pipe Tank", "Town Hall Area", "Nkubem", "Yalwa"],
        },
        "Mfantseman Municipal": {
            "Saltpond": ["Saltpond Central", "Mankessim", "Mankessim Market Area", "Anomabo", "Biriwa"],
        },
        "Assin Central Municipal": {
            "Assin Foso": ["Assin Foso Central", "Juaso", "Nyankumasi Ahenkro", "Assin Manso Slave River"],
        },
    },
    "Volta": {
        "Ho Municipal": {
            "Ho": ["Ho Central", "Bankoe", "Dome", "Heve", "Ahoe", "Fiave", "Kpodzi", "Sokode Etoe", "Sokode Lokoe", "UHAS Campus Area"],
        },
        "Hohoe Municipal": {
            "Hohoe": ["Hohoe Central", "Gbi Kpeme", "Wli Falls Area", "Fodome", "Alavanyo", "Likpe"],
        },
        "Kpando Municipal": {
            "Kpando": ["Kpando Central", "Kpando Torkor", "Gbefi", "Sovie"],
        },
        "Ketu South Municipal": {
            "Aflao": ["Aflao Border", "Denu", "Tokor", "Klikor", "Agbozume"],
        },
        "Keta Municipal": {
            "Keta": ["Keta Central", "Vodza", "Kedzi", "Dzelukope", "Tegbi", "Abutiakope"],
        },
        "South Tongu District": {
            "Sogakope": ["Sogakope Beach Area", "Sogakope Bridge Area", "Dabala", "Tefle"],
        },
        "North Tongu District": {
            "Battor": ["Battor Central", "Aveyime", "Juapong", "Mepe"],
        },
    },
    "Northern": {
        "Tamale Metropolitan": {
            "Tamale Central": ["Tamale Central", "Choggu", "Lamashegu", "Aboabo", "Changli", "Vittin", "Nyohini", "Salamba", "Kalariga"],
        },
        "Sagnarigu Municipal": {
            "Sagnarigu": ["Sagnarigu Central", "Kanvilli", "Kpasenkpe", "Gurarugu", "Dungu UDS Campus", "Education Ridge", "Jisonayili", "Choggu Manayili"],
        },
        "Savelugu Municipal": {
            "Savelugu": ["Savelugu Town", "Diare", "Moglaa", "Pong Tamale"],
        },
        "Yendi Municipal": {
            "Yendi": ["Yendi Central", "Nayilifong", "Gundogu", "Yendi Palace Area"],
        },
    },
    "Upper East": {
        "Bolgatanga Municipal": {
            "Bolgatanga": ["Bolga Central", "Soe", "Tanzui", "Zuarungu", "Yikene", "Sumbrungu", "Kumbosco"],
        },
        "Kassena Nankana Municipal": {
            "Navrongo": ["Navrongo Central", "UDS Navrongo Campus Area", "Paga Border", "Kologo"],
        },
        "Bawku Municipal": {
            "Bawku": ["Bawku Central", "Pusiga Road", "Garu Road", "Missiga"],
        },
    },
    "Upper West": {
        "Wa Municipal": {
            "Wa": ["Wa Central", "Kpaguri", "Dobile", "Kambali", "Bamahu UDS Campus", "Kabanye", "Nayiri", "Charingu"],
        },
        "Jirapa Municipal": {
            "Jirapa": ["Jirapa Town", "Hain", "Ullo", "Tizza"],
        },
        "Lawra Municipal": {
            "Lawra": ["Lawra Town", "Babile", "Eremon", "Zambo"],
        },
    },
    "Bono": {
        "Sunyani Municipal": {
            "Sunyani": ["Sunyani Central", "Fiapre", "Abesim", "Berlin Top", "Chiraa", "New Dormaa", "Penkwase", "Kotokrom", "Asufufu"],
        },
        "Berekum East Municipal": {
            "Berekum": ["Berekum Central", "Kato", "Senase", "Mpatapo", "Biadan"],
        },
        "Dormaa Central Municipal": {
            "Dormaa Ahenkro": ["Dormaa Central", "Kyeremasu", "Nkrankwanta", "Wamfie"],
        },
        "Wenchi Municipal": {
            "Wenchi": ["Wenchi Central", "Wurompo", "Subinso", "Tromeso"],
        },
    },
    "Bono East": {
        "Techiman Municipal": {
            "Techiman": ["Techiman Central Market", "Kentene", "Tuobodom", "Krobo", "Hansua", "Tanoana"],
        },
        "Kintampo North Municipal": {
            "Kintampo": ["Kintampo Waterfalls Area", "Kintampo Central", "Babatokuma", "Zongo Kintampo"],
        },
        "Atebubu Amantin Municipal": {
            "Atebubu": ["Atebubu Town", "Amantin Town", "Jato Zongo"],
        },
    },
    "Ahafo": {
        "Asunafo North Municipal": {
            "Goaso": ["Goaso Central", "Mim", "Akrodie", "Fawohoyeden"],
        },
        "Asutifi North District": {
            "Kenyasi": ["Kenyasi No 1", "Kenyasi No 2", "Ntotroso", "Gyaketey"],
        },
        "Tano North Municipal": {
            "Duayaw Nkwanta": ["Duayaw Nkwanta Town", "Bomaa", "Yamfo", "Tanoso Ahafo"],
        },
        "Tano South Municipal": {
            "Bechem": ["Bechem Central", "Techimantia", "Derma"],
        },
    },
    "Western North": {
        "Sefwi Wiawso Municipal": {
            "Sefwi Wiawso": ["Wiawso Central", "Dwinase", "Asafo", "Datano", "Kojina"],
        },
        "Bibiani Anhwiaso Bekwai Municipal": {
            "Bibiani": ["Bibiani Central", "Sefwi Bekwai", "Anhwiaso", "Awaso"],
        },
        "Juaboso District": {
            "Juaboso": ["Juaboso Central", "Bodi", "Bonsu Nkwanta", "Kwatwekrom"],
        },
    },
    "Oti": {
        "Krachi East Municipal": {
            "Dambai": ["Dambai Central", "Dambai Port Area", "Asukawkaw", "Katanga"],
        },
        "Nkwanta South Municipal": {
            "Nkwanta": ["Nkwanta Central", "Brewaniase", "Tutukpene", "Keri"],
        },
        "Jasikan Municipal": {
            "Jasikan": ["Jasikan Town", "Worawora", "Bodada", "Teteman"],
        },
        "Kadjebi District": {
            "Kadjebi": ["Kadjebi Central", "Poase Cement", "Dodo Pepesu", "Ahamansu"],
        },
    },
    "Savannah": {
        "West Gonja Municipal": {
            "Damongo": ["Damongo Central", "Mole National Park Area", "Larabanga", "Busunu"],
        },
        "East Gonja Municipal": {
            "Salaga": ["Salaga Central", "Kpembe", "Kafaba"],
        },
        "Central Gonja District": {
            "Buipe": ["Buipe Port", "Buipe Central", "Yapei", "Mpaha"],
        },
        "Bole District": {
            "Bole": ["Bole Central", "Bamboi", "Tinga", "Banda Nkwanta"],
        },
    },
    "North East": {
        "East Mamprusi Municipal": {
            "Nalerigu": ["Nalerigu Central", "Gambaga", "Langbinsi", "Sakogu"],
        },
        "West Mamprusi Municipal": {
            "Walewale": ["Walewale Central", "Wulugu", "Gbimsi", "Nasia"],
        },
        "Bunkpurugu Nakpanduri District": {
            "Bunkpurugu": ["Bunkpurugu Town", "Nakpanduri", "Bimbagu"],
        },
    },
}


class Command(BaseCommand):
    help = "Seed the database with all 16 Regions, their Districts, Towns, and Neighborhood Areas in Ghana."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing location data before seeding (warning: may affect properties linked to locations).",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting Ghana Locations database seeding..."))

        if options.get("clear"):
            self.stdout.write(self.style.WARNING("Clearing existing locations data..."))
            Area.objects.all().delete()
            Town.objects.all().delete()
            District.objects.all().delete()
            Region.objects.all().delete()

        regions_created = 0
        districts_created = 0
        towns_created = 0
        areas_created = 0

        with transaction.atomic():
            for region_name, districts_data in GHANA_LOCATIONS.items():
                region, r_created = Region.objects.get_or_create(name=region_name)
                if r_created:
                    regions_created += 1

                for district_name, towns_data in districts_data.items():
                    district, d_created = District.objects.get_or_create(
                        region=region,
                        name=district_name
                    )
                    if d_created:
                        districts_created += 1

                    for town_name, areas_list in towns_data.items():
                        town, t_created = Town.objects.get_or_create(
                            district=district,
                            name=town_name
                        )
                        if t_created:
                            towns_created += 1

                        for area_name in areas_list:
                            area, a_created = Area.objects.get_or_create(
                                town=town,
                                name=area_name
                            )
                            if a_created:
                                areas_created += 1

        invalidate_locations_cache()

        total_r = Region.objects.count()
        total_d = District.objects.count()
        total_t = Town.objects.count()
        total_a = Area.objects.count()

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded Ghana locations!\n"
            f"  - New added: {regions_created} regions, {districts_created} districts, {towns_created} towns, {areas_created} areas.\n"
            f"  - Total in DB: {total_r} Regions, {total_d} Districts, {total_t} Towns, {total_a} Areas across all 16 Regions of Ghana."
        ))
