#%%
import os
import re
import pickle
import pkgutil

#%%
class GenderExtractor:
    def __init__(self):
        """ Initializes the data.

        If it's the first time that this package is run, creates an index and saves it as pickle.
        Otherwise, it reads the premade file.
        """

        self.countries_encoding = {}
        self.names_lists = pkgutil.get_data(__name__, "nameLists/list.txt").decode().split(',')
        for fname in self.names_lists:
            text = os.path.split(fname.replace("\\", "/"))[-1]
            split = re.sub('([A-Z][a-z]+)', r' \1', re.sub('([A-Z]+)', r' \1', text)).split()
            country = split[0].lower()
            self.countries_encoding[country] = len(self.countries_encoding)-1

        self.gender_encoding = {"Male": 0, "Female": 1}

        try:
            self.name_freq = pickle.loads(pkgutil.get_data(__name__, "data.pickle"))
        except FileNotFoundError:
            self._create_pickle()
    
    def _create_pickle(self):
        """ Creates the index and saves it """
        self.name_freq = {}
        for fname in self.names_lists:
            fname = fname.strip().replace("\\", "/")
            text = os.path.split(fname)[-1]
            split = re.sub('([A-Z][a-z]+)', r' \1', re.sub('([A-Z]+)', r' \1', text)).split()
            country = split[0].lower()
            gender = split[1]
            gender_idx = self.gender_encoding[gender]
            country_idx = self.countries_encoding[country]

            names = pkgutil.get_data(__name__, fname).decode(encoding='utf-8').replace("\r", "").split('\n')
            processed = []
            for name in names:
                name_data = name.split(';')
                name = name_data[0].lower().strip()
                try: 
                    count = int(name_data[1].strip().replace('.',''))
                except IndexError:
                    if name in processed:
                        continue
                    count = 1

                try: 
                    self.name_freq[name][gender_idx][country_idx] += count
                except KeyError:
                    self.name_freq[name] = [[0]*len(self.countries_encoding), [0]*len(self.countries_encoding)]
                    self.name_freq[name][gender_idx][country_idx] += count
        
        save_loc = os.path.realpath(__file__)
        save_loc = os.path.dirname(save_loc)
        with open(save_loc+"/data.pickle", "wb") as f:
            pickle.dump(self.name_freq, f)

    def extract_gender(self, name, country=None):
        """ Extracts the suspected gender from the first name of a person.

        Args:
            name (str): First name. Case-insensitive.
            country (str, optional): Country that we're focusing. If none selected,
                the result will follow a general statistic. Case-insensitive.

        Returns:
            str: One of [male, mostly male, ambiguous, mostly female, female]
            
        Raises:
            KeyError: If country isn't in self.countries_encoding
        """
        name = name.lower()
        if country is None:
            country_code = None
        else:
            country = country.lower()
            country_code = self.countries_encoding[country]

        try:
            m_counts = self.name_freq[name][0]
            f_counts = self.name_freq[name][1]
        except KeyError:
            return "ambiguous"

        if country_code is not None:
            m_count = m_counts[country_code] + 1e-6
            f_count = f_counts[country_code] + 1e-6
        else:
            m_count = sum(m_counts) + 1e-6
            f_count = sum(f_counts) + 1e-6

        if m_count == 1e-6 and f_count == 1e-6:
            return "ambiguous"
        elif f_count / m_count > 0.9:
            return "female"
        elif f_count / m_count > 0.6:
            return "mostly female"
        elif m_count / f_count > 0.9:
            return "male"
        elif m_count / f_count > 0.6:
            return "mostly male"
        else:
            return "ambiguous"

if __name__=="__main__":
    ext = GenderExtractor()
