
# This is the Data Processing Script that gets all the DRC Internet data and outputs to a JSON file



from typing import final
import requests
import json
from collections import defaultdict
from itertools import combinations
from os import path
import pycristoforo as pyc
import math
from datetime import date
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from asnRank_download import AsnQuery, historic_data, print_help

countryCodes = ['cd']
countryNames = {'cd': 'Democratic Republic of the Congo'}
# Stores AS numbers of ASNs per country
countryASNs = {}

# Stores IXP PeeringDB ID's of IXPs in the country
countryIXPs = defaultdict(list)

# Info of each IXP - fields: name, lat, long, city, ipv4, ipv6(not always)
ixpInfo = defaultdict(dict)

# Info of each ASN - fields: name, lat, long, num connections (ppdc asses), ip
asnInfo = defaultdict(dict)

# ASNs at each IXP (using ID of IXP in countryIXPs as key and ASN number as value)
ixpMembers = defaultdict(list)

# asns belonging to an org, key = org value = list of asns belonging to that org
asnOrg = defaultdict(list)

# relationships by country
countryRelationships = defaultdict(list)

#dataframe with DRC IXPs and their interconnections points
interconnections_df = pd.DataFrame()

#dictionary to store DRC ASNrank Summary
DRC_asn_rank = []


# gets all ASNs given a Country as an argument from RIPEstat api, populates country ASNs
def getCountrysASNs(country):
    # making the API call
    url = 'https://stat.ripe.net/data/country-asns/data.json?resource={0}&lod=1'.format(
        country)

    response = requests.get(url)

    if (response.ok):
        jData = json.loads(response.content)

        rawRouted = jData['data']['countries'][0]['routed'][1:-1]
        rawNonRouted = jData['data']['countries'][0]['non_routed'][1:-1]
        routedASNs = rawRouted.split(', ')
        nonroutedASNs = rawNonRouted.split(', ')

        # getting all ASNs by country
        allASNs = routedASNs + nonroutedASNs

        # formatting the data
        i = 0
        for asn in allASNs:
            allASNs[i] = asn[10:-1]
            i += 1

        allASNs = [x for x in allASNs if x != '']
        # adding to the dictionary
        countryASNs[country] = allASNs
    else:
        # If response code is not ok (200), print the resulting http error code with description
        response.raise_for_status()

# gets all DRC IXPs dictionary from perringDB api
def getCountryIXPs():
    # making the API call
    url = 'https://www.peeringdb.com/api/ix?country=CD'
    response = requests.get(url)

    if response.ok:
        jData = json.loads(response.content)
        jData = jData[next(iter(jData))]

        for x in jData:
            # storing ids of ixps per country
            countryIXPs[x['country'].lower()].append(x['id'])
            #countryIXPs[x['country'].lower()].append(x['name'])
            #countryIXPs[x['country'].lower()].append(x['city'])

    else:
        # If response code is not ok (200), print the resulting http error code with description
        response.raise_for_status()

# poputlates ixpMembers dict with ASNs connected to the specific IXP
def get_IXP_Members(ixp):
    # ixp = id of ixp in countryIXPs
    # returns a list of asns at the ixp
    url = 'https://www.peeringdb.com/api/net?ix={0}'.format(ixp)

    response = requests.get(url)

    if (response.ok):
        jData = json.loads(response.content)
        jData = jData[next(iter(jData))]

        for x in jData:
            ixpMembers[ixp].append(x['asn'])
        

    else:
        # If response code is not ok (200), print the resulting http error code with description
        response.raise_for_status()
    
    

# gets asn location using the asn number using RIPEstat api and maxmind geo lite
# preferred over prefix method due to 1 less api call required per asn
def get_ASN_Location_byASN(asn):
    url = 'https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS{0}'.format(
        asn)

    response = requests.get(url)

    if (response.ok):
        jData = json.loads(response.content)
        if (len(jData['data']['located_resources']) > 0):

            locations = jData['data']['located_resources']

            # saving the coordinates
            for location in locations:
                if (location['locations'][0]['country'].lower() in countryCodes):
                    asnInfo[asn]['lat'] = location['locations'][0]['latitude']
                    asnInfo[asn]['long'] = location['locations'][0]['longitude']
                    return

    else:
        # If response code is not ok (200), print the resulting http error code with description
        response.raise_for_status()

# gets asn holder name from RIPEstat api
def get_ASN_Info(asn):
    url = 'https://stat.ripe.net/data/as-overview/data.json?resource=AS{0}'.format(
        asn)

    if (asn in asnInfo.keys()):
        response = requests.get(url)

        if (response.ok):
            jData = json.loads(response.content)
            # saving the name
            name = jData['data']['holder']
            if (name != 'null'):
                asnInfo[asn]['holder'] = name

        else:
            # If response code is not ok (200), print the resulting http error code with description
            response.raise_for_status()
    else:
        return


# gets organisations asn belongs from peeringDB api, to determine s2s relationships
def getOrg(asn):

    url = 'https://www.peeringdb.com/api/net?asn={0}'.format(asn)
    #url = 'https://www.peeringdb.com/api/org?asn={0}'.format(asn)

    response = requests.get(url)

    
    
    try:
        if (response.ok):
            jData = json.loads(response.content)

            if (len(jData['data']) > 0):
                # assigning the asn in the parameter to it's orgs key in the dictionary
                asnOrg[jData['data'][0]['id']].append(asn)

            else:
                return

        # else:
        #     # If response code is not ok (200), print the resulting http error code with description
        #     response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(err)

# get CAIDA relationship data and determine ASN priority based on it's number of connections
def determine_ASN_Priorities():
    # read in the pre filtered CAIDA data file
    f = open(path.relpath('CAIDA_Data/priorities.json'))
    priorities = json.load(f)
    f.close()
    # saving the priority
    try:
        for x in asnInfo:
            import ast
            #my_string = "{'key':'val','key2':2}"
            y = ast.literal_eval(x)
            if y not in priorities.keys():
                continue
            y['Priority'] = priorities[y]
    except KeyError:
        print('An ASN was not found')

# determines s2s relationships by linking asns that belong to the same organisation
def get_S2S_Rels():
    print(asnOrg.values())

    for asns in asnOrg.values():
        # more than 1 asn required for a relationship
        if (len(asns) > 1):

            # getting all possible relationships between sibling ASNs using combinations library
            pairs = list(combinations(asns, 2)) 
            for pair in pairs:
                relDict = {}
                pair = str(pair)[1:-1]
                sib1 = pair.split(', ')[0]
                sib2 = pair.split(', ')[1]
                country = ''

                # saving the new S2S relationship if valid
                relDict['Sibling1'] = sib1[1:-1]
                relDict['Sibling2'] = sib2[1:-1]
                relDict['Type'] = 'S2S'

                if (relDict['Sibling1'] in asnInfo.keys()):
                    if (relDict['Sibling2'] in asnInfo.keys()):

                        for y in countryASNs.keys():
                            if (relDict['Sibling1'] in countryASNs[y]):
                                country = y
                                break
                        countryRelationships[country].append(relDict)


# get CAIDA relationship data and determine p2p and p2c relationships between ASNs
def get_P2P_P2C_Rels():
    # reads in the pre filtered CAIDA data file
    h = open(path.relpath('CAIDA_Relationship_Data/P2P_P2C_Rels.json'))

    otherRels = json.load(h)

    # saving the relationships
    for k in otherRels.values():
        for p in k:
            del p['Protocol']

    for j in otherRels.keys():
        for l in otherRels[j]:
            countryRelationships[j].append(l)



# Focus on DRC CAIDA AsnRank API version 2: Using GraphQL
def DRC_asnRank():
    temp_Rank = []
    URL = "https://api.asrank.caida.org/v2/graphql"
    for asn in countryASNs.values():
        for a in asn:
            i =0
            query = AsnQuery(int(a)) # function from asnRank-downoad.py script
            request = requests.post(URL,json={'query':query})
            if request.status_code == 200:
            
                datapoint = request.json()
                temp_Rank.append(datapoint)
                
            else:
                print ("Query failed to run returned code of %d " % (request.status_code))
    

    for dat in temp_Rank:
        for v in dat.values():
            DRC_asn_rank.append(v)
    
    df = pd.DataFrame()
    df = DRC_asn_rank.toDat
    df.to_csv('drc_asnran.csv', sep='\t')
    
    with open("AsnRank.json", "w") as file:
        json.dump([ob for ob in DRC_asn_rank], file)



#queries for historical ASNCone data : passed a List of ASNs of a Country
def DRC_hist():
    historic_Rank = []
    
    URL = "https://api.asrank.caida.org/v2/graphql"
    for asns in countryASNs.values():
        #asn_data = dict()
        for asn in asns:    
            i =0
            query = historic_data(int(asn))
            request = requests.post(URL,json={'query':query})
            if request.status_code == 200:
                print(request.json())
                asn_data = request.json()['data']['asns']['edges']
                for node in asn_data:
                    historic_Rank.append(node.values())
                
            else:
                print ("Query failed to run returned code of %d " % (request.status_code))
    
    print('=======writing Historical to CSV======')
    historic_df = pd.DataFrame(historic_Rank)
    historic_df.to_csv('drc_historic.csv', sep='\t')


#main function that executes the functions above : Note that some of the functions are commented out to reduce the execution time
def main():
    getCountrysASNs('CD')
    print('List of DRC ASNs :{}',countryASNs)
    print('========================================================')

    getCountryIXPs()
    print('List of DRC IXPs {}',countryIXPs)
    ixpnumbers= []
    for k, v in countryIXPs.items():
        for c in v:
            ixpnumbers.append(c)
    
    
    for ixpnum in ixpnumbers:
        get_IXP_Members(ixpnum)
    
    print('==========Getting IXPs and their members============')
    print(ixpMembers)
    
    
    # print('Getting ASN info and location')
    # # get asn info and location
    # for z in countryASNs.values():
    #     for w in z :
    #         get_ASN_Location_byASN(w)
    #         get_ASN_Info(w)
    #         getOrg(w)
    
    # print('============== ASN organisations and their clients======================')
    # print(asnOrg)
    # print('==============Determining ASN priorities==============') : Takes sometime 2-3 minutes to finish executing
    # determine_ASN_Priorities()

    print ("=============================DRC ASNs CAIDA ASNRank========================")
    #DRC_asnRank()
    print(DRC_asn_rank)

    print("============DRC historical ASN Cone data") #
    DRC_hist()

    print(asnInfo)
    print("==========================================")
    get_S2S_Rels()
    print(countryRelationships)

    #TODO '''Trying to draw Ixp members with networkx through a Dataframe'''
    #print(ixpMembers)
    interconnections_df = pd.DataFrame(ixpMembers.items(), columns=['ixpnum','members'])
    #df3 = interconnections_df['members'].split(',', expand=True)
    #interconnections_df[['ixpnum','members']] = interconnections_df['members'].str.split(',',expand=True)
    # print(interconnections_df.iloc[1])
    G = nx.Graph()
    options = ['r','b']
    colors = []
    color_map = []
    for x in range(0, len(interconnections_df)):
        obj = interconnections_df.iloc[x]
        nodes = obj['ixpnum']
        for z in obj['members']:
            G.add_edge(nodes,z, color='r')
            
            for node in G:
                if node < 3:
                    color_map.append('yellow')
                else: 
                    color_map.append('green')
    import sys
    #pos = nx.nx_agraph.graphviz_layout(G)
    #nx.drawing.nx_pydot.write_dot(G,sys.stdout)            
    #nx.draw(G, node_color=color_map,with_labels=True)
    
    
    plt.show()
    
    
if __name__ == '__main__':
    main()



#layer1 :  Point d reception internet (Submarine cables)
# the fixed vs the mobile 
#FAI premier niveau
#eyeballs  vs transits networks
# are the eyeball networks interconnected?
# Paper Document that covers the methodology used so far
# push everything to GitHUb and share the repo with Josiah
#differenciate the upstream vs downstream ASNs, are they peering with each other, respectively?
#Correct the Networkx RIPE Left-Right ASN relationship graph : remove the repeated nodes
#Aggreate DRC ASN rank historical data by a Month : Focus on asnRank metric alone at start
#https://stat.ripe.net/data/country-resource-list/data.json?resource=CD
#https://api.bgpview.io/asn/37020/peers
#https://api.asrank.caida.org/v2/docs
#https://stats.labs.apnic.net/cgi-bin/aspop?c=CD