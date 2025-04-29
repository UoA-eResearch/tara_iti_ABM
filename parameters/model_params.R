# load packages 
library(tidyverse)

# load in data 
egg_25 <- read.csv("./raw_data/egg_level_data_2000_2025.csv")
capture_morph_25 <- read.csv("./raw_data/captures_morphometrics_data_1990_2025.csv")
# need to get sighting data from ilse 

# little tidy to sort out date columns 
egg_25$Year <- (egg_25$season) %>%  
  substr(1, 4) 
egg_25$Year <- as.numeric(egg_25$Year)

egg_25$estimated_lay <- dmy(egg_25$estimated_lay)
egg_25$hatched_date <- dmy(egg_25$hatched_date)


capture_morph_25$Date <- dmy(capture_morph_25$Date)
capture_morph_25$Year <- year(capture_morph_25$Date)

# what parameters do i need: 

# sex ratio - get sightings data to deal with this better 
sex_breakdown <- capture_morph_25 %>% 
  filter(Year > 1999) %>%
  distinct(Band_Number, .keep_all = T) %>% # select distinct birds, but keep all variables
  summarise(males = sum(sex_verified == "male"), 
            females = sum(sex_verified == "female"))

# look at breeding dynamics 
# male breeding age 
m_age_mean <- mean(egg_25$m_age, na.rm = T)
m_age_min <- min(egg_25$m_age, na.rm = T)
m_age_max <- max(egg_25$m_age, na.rm = T)
# mean female breeding age 
f_age_mean <- mean(egg_25$f_age, na.rm = T)
f_age_min <- min(egg_25$f_age, na.rm = T)
f_age_max <- max(egg_25$f_age, na.rm = T)

# plot them together 
egg_25 %>% 
  group_by(Year) %>% 
  summarise(male = mean(m_age, na.rm = TRUE), 
            female = mean(f_age, na.rm = TRUE)) %>% 
  pivot_longer(cols = c(male, female),
               names_to = "sex", values_to = "age_mean") %>% 
  ggplot(aes(x = Year, y = age_mean, color = sex)) +
  geom_line() +
  theme_minimal() + 
  labs(y = "Mean breeding age", color = "Sex")
  
# mean proportion of females breeding 
# average age 
# life stage breakdown 
# average population size 

# mean number of clutches  
clutches <- egg_25 %>%
  group_by(season) %>%
  summarise(clutch_1 = sum(clutch_no == "1"), 
            clutch_2 = sum(clutch_no == "2"), 
            clutch_3 = sum(clutch_no == "3")) %>% 
  ungroup()

mean_clutch_1 <- mean(clutches$clutch_1, na.rm = T)
mean_clutch_2 <- mean(clutches$clutch_2, na.rm = T)
mean_clutch_3 <- mean(clutches$clutch_3, na.rm = T)

# pivot longer (for plotting)
clutch_long <- clutches %>%
  pivot_longer(
    cols = starts_with("clutch"), 
    names_to = "clutch_no", 
    values_to = "egg_no"
  )

# plot it 
ggplot(clutch_long, aes(x = season, y = egg_no, fill = clutch_no)) +
  geom_bar(stat = "identity", position = "dodge") +
  labs(x = "Season", y = "Number of eggs", fill = "Clutch number") +
  theme_minimal()

# pull out clutch 1 
clutch1 <- egg_25 %>% 
  filter(clutch_no == "1") %>% 
  group_by(season, nest_id) %>% # look at each nest 
  summarise(clutch_size = n()) %>% # clutch size is equal to number of rows (n of eggs)
  ungroup()

# pull out clutch 2 
clutch2 <- egg_25 %>% 
  filter(clutch_no == "2") %>% 
  group_by(season, nest_id) %>% # look at each nest 
  summarise(clutch_size = n()) %>% # clutch size is equal to number of rows (n of eggs)
  ungroup()

# pull out clutch 2 
clutch3 <- egg_25 %>% 
  filter(clutch_no == "3") %>% 
  group_by(season, nest_id) %>% # look at each nest 
  summarise(clutch_size = n()) %>% # clutch size is equal to number of rows (n of eggs)
  ungroup()

# mean clutch size 
mean_clutch1 <- clutch1 %>% 
  group_by(season) %>% 
  summarise(mean_clutch1 = mean(clutch_size)) %>% 
  ungroup()

mean_clutch2 <- clutch2 %>% 
  group_by(season) %>% 
  summarise(mean_clutch2 = mean(clutch_size)) %>% 
  ungroup()

mean_clutch3 <- clutch3 %>% 
  group_by(season) %>% 
  summarise(mean_clutch3 = mean(clutch_size)) %>% 
  ungroup()

# combine them 
mean_clutch_all <- mean_clutch1 %>%
  left_join(mean_clutch2, by = "season") %>%
  left_join(mean_clutch3, by = "season")

# Pivot longer
mean_clutch_long <- mean_clutch_all %>%
  pivot_longer(
    cols = starts_with("mean_clutch"), 
    names_to = "clutch_no", 
    values_to = "mean_size"
  )

# plot it 
ggplot(mean_clutch_long, aes(x = season, y = mean_size, fill = clutch_no)) +
  geom_bar(stat = "identity", position = "dodge") +
  labs(x = "Season", y = "Mean Clutch Size", fill = "Clutch number") +
  theme_minimal()



# breeding season length 
breeding_season_length <- egg_25 %>% 
  group_by(season) %>% 
  summarise(first_lay = min(estimated_lay, na.rm = T), 
            last_lay = max(estimated_lay, na.rm = T)) %>% 
  ungroup()
# earliest lay 16th October 
# latest lay 28th January 

# incubation length 
# hatch date - lay date 
incubation <- egg_25 %>% 
  mutate(incubation_length = hatched_date - estimated_lay) %>% 
  filter(incubation_length > 0 & incubation_length < 40) # negative numbers equate to errors in the data input
 
# what is the mean (23 days)
mean_incubation_length <- mean(incubation$incubation_length, na.rm = T)

# look at the mean per season, by clutch number 
incubation_time_series <- egg_25 %>% 
  mutate(incubation_length = hatched_date - estimated_lay, na.rm = T) %>% 
  filter(incubation_length > 0 & incubation_length < 40) %>%
  group_by(season, clutch_no) %>% 
  summarise(mean_incubation_length = mean(incubation_length, na.rm = T)) %>% 
  ungroup()

# plot it 
ggplot(incubation_time_series, aes(x = season, y = mean_incubation_length, 
                                   group = as.character(clutch_no), 
                                   colour = as.character(clutch_no))) +
  geom_line() +
  labs(x = "Season", y = "Mean incubation length", colour = "Clutch number") +
  theme_minimal()

# look at fertility across clutches 
clutch_fertility <- egg_25 %>% 
  group_by(season, clutch_no) %>% 
  summarise(
    no_eggs = n(),
    fertile = sum(fertile == "1")) %>% 
  ungroup()

# look at hatch success across clutches 


# some measure of fertility 
fertility <- egg_25 %>% 
  group_by(season) %>% 
  summarise(no_eggs = n(), 
            fertile_eggs = sum(fertile == "1"), 
            fertility_rate = fertile_eggs/no_eggs) %>% 
  ungroup()

mean_fertility <- mean(fertility$fertility_rate) 

# birds have differing rates of fertility - investigate this further 
# female fertility 
female_fertility <- egg_25 %>% 
  filter(female_id != "unbanded female") %>% 
  group_by(female_id) %>% 
  summarise(no_eggs = n(), 
            fertile_eggs = sum(fertile == "1"), 
            fertile_rate = fertile_eggs/no_eggs) %>% 
  ungroup()

# make a histogram of this 
ggplot(female_fertility, aes(x = fertile_rate)) + 
  geom_histogram(binwidth = 0.075) + 
  theme_bw()

# male fertility 
male_fertility <- egg_25 %>% 
  filter(male_id != "unbanded female") %>% 
  group_by(male_id) %>% 
  summarise(no_eggs = n(), 
            fertile_eggs = sum(fertile == "1"), 
            fertile_rate = fertile_eggs/no_eggs) %>% 
  ungroup()

# make a histogram of this 
ggplot(male_fertility, aes(x = fertile_rate)) + 
  geom_histogram(binwidth = 0.075) + 
  theme_bw()
  

# hatch success 
hatch_success <- egg_25 %>% 
  group_by(season) %>% 
  summarise(no_eggs = n(), 
            hatched_eggs = sum(hatched == "1"), 
            hatch_rate = hatched_eggs/no_eggs, 
            failure_rate = 1 - (hatched_eggs/no_eggs)) %>% 
  ungroup()

mean_hatch_failure <- mean(hatch_success$failure_rate, na.rm = T)
# do the same but only consider fertile eggs
hatch_success_fertile <- egg_25 %>% 
  filter(fertile == "1") %>%
  group_by(season) %>% 
  summarise(no_eggs = n(), 
            hatched_eggs = sum(hatched == "1"), 
            hatch_rate = hatched_eggs/no_eggs, 
            failure_rate = 1 - (hatched_eggs/no_eggs)) %>% 
  ungroup()

mean_fertileHatch_failure <- mean(hatch_success_fertile$failure_rate)

# breakdown of hatch failure causes 

# mortality causes at each life stage 

