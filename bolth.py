from IPython.display import display
from folium.plugins import HeatMap
from folium import Map
import numpy as np
import pandas as pd
    
zip_lookup = pd.read_csv(r'/Users/johnboesen/Documents/Code/Bolth-Heatmap/zips.csv', sep=',',header=None)
for i, r in zip_lookup.iterrows():
    if i == 0:
        continue
    r[1] = float(r[1])
    r[2] = float(r[2])
zip_list = list(zip_lookup[0])
for i, e in enumerate(zip_list[1:]):
    zip_list[i] = int(e)

# Iterative Binary Search Function method Python Implementation  
# It returns index of n in given list1 if present,   
# else returns -1   
def binary_search(n):
    try:
        n = int(n)
    except ValueError:
        return -1
    if n < 601 or n > 99929:
        return -1
    global zip_list
    list1 = zip_list
    low = 0  
    high = len(list1) - 1  
    mid = 0  
    
    while low <= high:  
        # for get integer result   
        mid = (high + low) // 2  

        # Check if n is present at mid   
        if list1[mid] < n:  
            low = mid + 1  
    
        # If n is greater, compare to the right of mid   
        elif list1[mid] > n:  
            high = mid - 1  
    
        # If n is smaller, compared to the left of mid  
        else:  
            return mid  
    
            # element was not present in the list, return -1  
    return -1  
    
    
def zip_to_coords(zip):

    zip_ind = binary_search(zip)
    if zip_ind == -1:
        return [None, None]
    # print(zip_lookup.columns)
    # print ([zip_lookup.iloc[zip_ind + 1][1], zip_lookup.iloc[zip_ind][2]])
    return [zip_lookup.iloc[zip_ind + 1][1], zip_lookup.iloc[zip_ind + 1][2]]
    # for i, r in zip_lookup.iterrows():
    #     if r[0] == zip:
    #         # lat, long
    #         return [r[1], r[2]]

# import csv
# change csv to df
df = pd.read_csv(r'/Users/johnboesen/Documents/Code/Bolth-Heatmap/both.csv', sep=',',header=None)
# find instances of bolth
# create dataframe that stores lat and longs of bolthers
coords = pd.DataFrame(columns=["lat", "lng"])
# for each column in the dataframe
for i, r in df.iterrows():
    # if they don't pronounce it right
    if r[1] != "bowlth or bolth: there's an \"L\" sound, like \"bowl\" plus \"th\"":
        current_coords = zip_to_coords(r[5])
        # if the user didn't suck at zips
        if current_coords[0]:
            # add coords to list
            coords.loc[len(coords)] = current_coords

display(coords)

map = Map(location=[41.169621, -97.683617], zoom_start=8)

# hm_wide = HeatMap(
#     list(zip(for_map.latitude.values, for_map.longitude.values)),
#     min_opacity=0.2,
#     radius=17, 
#     blur=15, 
#     max_zoom=1,
# )
HeatMap(coords).add_to(map)

print(type(map))

map.save("heatmap.html")

