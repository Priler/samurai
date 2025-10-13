import re
from configurator import config, make_config
from utils import Gender, remove_non_letters, detect_name_language, detect_gender__compare, transliterate_name, name_strip_suffixes, name_norm, prepare_word

make_config("config.ini")

def detect_gender(name: str) -> Gender:
    # remove any non-letters (emoji etc)
    _name = name
    name = remove_non_letters(name)

    FEMALE_SUFFIXES = [
        "очка", "ечка", "юшка", "енька", "инка", "ушка", "ка", "ша", "уся", "юся", "ся",
        "онька", "ень", "еньки", "юнька",
    ]

    MALE_SUFFIXES = [
        "ик", "ек", "ёк", "ок", "чик",
        "яша", "юша", "ёша", "ян"
    ]

    # pre-process the name
    if name:
        try:
            # prepare the name
            name = next(
                (part for part in name.split() if part.strip() and len(part.strip()) > 1),
                None
            )

        except AttributeError:
            name = _name # restore OG
    else:
        name = _name # restore OG name (nicknames like "." or "$" etc)

    # preprocess name
    _name_lang = detect_name_language(name)
    name = prepare_word(name)  # fix mask letters ('h' as 'н', etc.)
    name = transliterate_name(name, 'english' if _name_lang == 'russian' else 'english')

    print(name)
    print(_name_lang)

    if _name_lang == 'russian':
        det_gen = detect_gender__compare(name, "Russia")

        if det_gen == Gender.UNKNOWN:
            # dedup letters and try again
            dedupped_name = re.sub(r'([А-Яа-яЁё])\1+', r'\1', name)
            det_gen = detect_gender__compare(dedupped_name, "Russia")

            # print(dedupped_name)
            # print(_name_lang)

            if det_gen == Gender.UNKNOWN:
                # try to detect based on suffixes
                # and try/detect again
                name = name_norm(name)

                if name != name_strip_suffixes(name, FEMALE_SUFFIXES):
                    det_gen = Gender.FEMALE
                elif name != name_strip_suffixes(name, MALE_SUFFIXES):
                    det_gen = Gender.MALE

                # print("SSS ", name)
                # print("SSS ", det_gen)

                # det_gen = detect_gender__compare(name, "Russia")

                if det_gen == Gender.UNKNOWN:
                    # if gender is still unknown, try to transliterate it and compare again

                    det_gen = detect_gender__compare(transliterate_name(name), "USA")

    elif _name_lang == 'english':
        det_gen = detect_gender__compare(name, "USA")

        # if gender unknown, try to transliterate it and compare again
        if det_gen == Gender.UNKNOWN:
            det_gen = detect_gender__compare(transliterate_name(name), "Russia")

    else:
        det_gen = detect_gender__compare(name)

    # return result, whatever it will be
    return det_gen
    # last shot
    # if name ends with 'а' letter, then assume it's female
    # return Gender.FEMALE if name not in ["фома", "савва", "кима", "алима"] and name.lower()[-1] == 'а' else Gender.UNKNOWN

# print("DET: ", detect_gender(":)[Nikita]"))
# print("DET: ", detect_gender("Hasтюшкаааа"))
# print("DET: ", detect_gender("пpофuль"))
# print("DET: ", detect_gender("пр0филь"))
# print("DET: ", detect_gender("у б0тоB для aнтucπаmа с/\\0Вa 4ymb-4ymb uck0Bepkaнbl 😁"))

# name_valid = True
# nsfw_prediction = {
#     "Normal": 0.54,
#     "Enticing or Sensual": 0.18,
#     "Pornography": 0.27,
#     "Anime Picture": 0.01,
#     "Hentai": 0
# }
#
# if (not name_valid or (
#         # safe checks (allowed detections)
#         not (
#             (float(nsfw_prediction["Normal"]) > float(config.nsfw.normal_prediction_threshold)
#             or float(nsfw_prediction["Anime Picture"]) > float(config.nsfw.anime_prediction_threshold))
#             and
#             (
#                     float(nsfw_prediction["Enticing or Sensual"]) < float(config.nsfw.normal_comb_sensual_prediction_threshold)
#                     and
#                     float(nsfw_prediction["Pornography"]) < float(config.nsfw.normal_comb_pornography_prediction_threshold)
#             )
#         )
#
#         # unsafe checks (disallowed detections)
#         and (
#                 # check this flags with AND condition (both should return True to be detected as NSFW
#                 (float(nsfw_prediction["Enticing or Sensual"]) > float(config.nsfw.comb_sensual_prediction_threshold)
#                  and float(nsfw_prediction["Pornography"]) > float(config.nsfw.comb_pornography_prediction_threshold))
#
#                 # separate detections
#                 or float(nsfw_prediction["Enticing or Sensual"]) > float(config.nsfw.sensual_prediction_threshold)
#                 or float(nsfw_prediction["Pornography"]) > float(config.nsfw.pornography_prediction_threshold)
#                 or float(nsfw_prediction["Hentai"]) > float(config.nsfw.hentai_prediction_threshold))
# )):
#     print("NFSW detected")
# else:
#     print("Image is clear.")