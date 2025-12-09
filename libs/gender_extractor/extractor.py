# %%
import os
import re
import pickle
import pkgutil

# %%


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
            self.countries_encoding[country] = len(self.countries_encoding) - 1

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

            names = pkgutil.get_data(__name__, fname).decode(
                encoding='utf-8').replace("\r", "").split('\n')
            processed = []
            for name in names:
                name_data = name.split(';')
                name = name_data[0].lower().strip()
                try:
                    count = int(name_data[1].strip().replace('.', ''))
                except IndexError:
                    if name in processed:
                        continue
                    count = 1

                try:
                    self.name_freq[name][gender_idx][country_idx] += count
                except KeyError:
                    self.name_freq[name] = [[0] *
                                            len(self.countries_encoding), [0] *
                                            len(self.countries_encoding)]
                    self.name_freq[name][gender_idx][country_idx] += count

        save_loc = os.path.realpath(__file__)
        save_loc = os.path.dirname(save_loc)
        with open(save_loc + "/data.pickle", "wb") as f:
            pickle.dump(self.name_freq, f)

    def extract_gender(self, name, country=None):
        """Extracts the suspected gender from the first name of a person.

        The function uses statistical data to determine the likely gender associated
        with a given first name, optionally taking into account country-specific data.
        A small epsilon value (1e-6) is added to counts to avoid division by zero.

        Args:
            name (str): First name of the person. Case-insensitive.
            country (str, optional): Country to focus analysis on. If None,
                uses global statistics. Case-insensitive.

        Returns:
            str: Gender category, one of:
                - "male" (>90% male)
                - "mostly male" (60-90% male)
                - "ambiguous" (40-60% either gender)
                - "mostly female" (60-90% female)
                - "female" (>90% female)
                - "female and male" (50/50 when female/male in the same time, ie russian name "Саша")

        Raises:
            KeyError: If the provided country is not in self.countries_encoding
            TypeError: If name or country are not strings when provided
            ValueError: If name is empty or contains only whitespace
        """
        # Input validation
        if not isinstance(name, str):
            raise TypeError("Name must be a string")
        if country is not None and not isinstance(country, str):
            raise TypeError("Country must be a string or None")

        # Normalize inputs
        name = name.lower().strip()

        # Check for empty name after stripping
        if not name:
            raise ValueError("Name cannot be empty or contain only whitespace")

        if country is not None:
            country = country.lower().strip()
            country_code = self.countries_encoding[country]
        else:
            country_code = None

        # Get gender frequency counts
        try:
            m_counts = self.name_freq[name][0]
            f_counts = self.name_freq[name][1]
        except KeyError:
            return "ambiguous"

        # Calculate relevant counts with epsilon to avoid division by zero
        epsilon = 1e-6
        if country_code is not None:
            m_count = m_counts[country_code] + epsilon
            f_count = f_counts[country_code] + epsilon
        else:
            m_count = sum(m_counts) + epsilon
            f_count = sum(f_counts) + epsilon

        # Return early if no meaningful data
        if m_count == epsilon and f_count == epsilon:
            return "ambiguous"

        # Calculate ratios and determine gender category
        female_ratio = f_count / m_count
        male_ratio = m_count / f_count

        if female_ratio == male_ratio:
            return "female and male"  # name is both male/female
        elif female_ratio > 9:  # >90% female
            return "female"
        elif female_ratio > 1.5:  # 60-90% female
            return "mostly female"
        elif male_ratio > 9:  # >90% male
            return "male"
        elif male_ratio > 1.5:  # 60-90% male
            return "mostly male"
        else:  # 40-60% either gender
            return "ambiguous"


if __name__ == "__main__":
    ext = GenderExtractor()
