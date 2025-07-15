import os
import requests
import json

# Author: Alexis Finch
#
# Date: July 5, 2023
#
# The purpose of this program is to present a list of cost indexes for Manufacturing and Reactions for an alliance
# (or alliances) in EVE Online
# The data can then be sent to Discord or Slack
#
# Set it up on a CRON job or task scheduler to cycle regularly, and it'll keep you up to date on the cost indexes
# in your systems!


# Formats indexes for sake of readability. Converts decimals into percentages.
def indexFormatter(index):
    return f"{index:.2%}"

# Helper filter function to get the correct array index for the cost
def is_activity(what):
    return lambda x: x['activity'] == what

def parseIndicesBySystemList(index_response, alliance_systems, config = None):
    indices_list = {}
    if config and len(config) > 0:
        for k in config.keys():
            indices_list[k] = []

    # Reads through all indexes returned by ESI
    for cost_index in index_response:
        # Then checks the list of system IDs in the alliance systems list, to see if it's on the list
        for system in alliance_systems:
            # If the systems match (cost index pertains to a system on the alliance_systems list
            if cost_index['solar_system_id'] == system['id']:
                ci = cost_index['cost_indices']
                for k in config.keys():
                    cix = list(filter(is_activity(k), ci))
                    if cix and cix[0]['cost_index'] > configuration['display_threshold']:
                        indices_list[k].append([system['name'], cix[0]['cost_index']])

    # sorts the data
    for k in indices_list.keys():
        indices_list[k].sort(key=lambda x: x[1])
        indices_list[k].reverse()

    return indices_list


def buildOutputString(indices_list, config = None):
    outputString = ""

    first = True
    for i in config.keys():
        if not config[i]['enabled']:
            continue

        if first:
            outputString += "\n"
            first = False
        outputString += "{} Cost Index Report:\n\n```\n".format(config[i]['display_name'])

        if not indices_list[i]:
            outputString += "Nothing to report.\n"
            continue

        for system in indices_list[i]:
            system[1] = indexFormatter(system[1])
            outputString += ('{0:7} {1:>8}'.format(*system)) + "\n"

        outputString += "```\n\n"

    return outputString.rstrip()


def filterByRegions(alliance_systems):
    inRegionFilteredList = []
    resolve_region_id_url = 'https://esi.evetech.net/latest/universe/regions/'
    resolve_constellation_id_url = 'https://esi.evetech.net/latest/universe/constellations/'

    for region in configuration['regions']:
        regionJSON = requests.get(resolve_region_id_url+str(region)).json()
        for constellation in regionJSON['constellations']:
            constellationJSON = requests.get(resolve_constellation_id_url+str(constellation)).json()
            for system in constellationJSON['systems']:
                for trackedSystem in alliance_systems:
                    if system == trackedSystem['id']:
                        inRegionFilteredList.append(trackedSystem)

    return inRegionFilteredList


def postSlackWebhook(content):
    # Pulls the slack URL from the ENV Variable
    slack_url = os.environ["INDY_BOT_SLACK_WEBHOOK_URL"]

    # Sends it in the proper format, to the slack webhook
    requests.post(slack_url, data=json.dumps({'text': content}), headers={'Content-Type': 'application/json'})


def postDiscordWebhook(content):
    # Pulls the discord webhook URL from the ENV variable
    discord_url = os.environ['INDY_BOT_DISCORD_WEBHOOK_URL']

    # Sends it in the proper format, to the discord webhook
    requests.post(discord_url, data=json.dumps({'content': content}), headers={'Content-Type': 'application/json'})


def GetIndices(alliance_IDs):
    sov_url = 'https://esi.evetech.net/latest/sovereignty/structures/'
    indices_url = 'https://esi.evetech.net/latest/industry/systems/'

    sov_response = requests.get(sov_url).json()

    alliance_systems = []

    for system in sov_response:
        if system['alliance_id'] in alliance_IDs and (system['structure_type_id'] == 32458 or
                                                      system['structure_type_id'] == 32226):
            if system['solar_system_id'] not in alliance_systems:
                alliance_systems.append(system['solar_system_id'])

    resolve_system_name_url = 'https://esi.evetech.net/latest/universe/names/'
    alliance_systems = requests.post(resolve_system_name_url,
                                     headers={'Accept': 'application/json', 'Content-Type': 'application/json',
                                              'Cache-Control': 'no-cache'},
                                     json=alliance_systems).json()

    alliance_systems = filterByRegions(alliance_systems)

    index_response = requests.get(indices_url).json()

    # Determine which indices to display and how they should be called here
    config_idx = {}
    if 'enabled_indices' in configuration:
        config_enabled = configuration['enabled_indices']
        config_display = {
            'manufacturing': "Manufacturing",
            'reaction': "Reaction",
            'researching_material_efficiency': "ME Research",
            'researching_time_efficiency': "TE Research",
            'invention': "Invention",
            'copying': "Copying"
        }
        for k in config_display.keys():
            if k in config_enabled:
                config_enabled[k] = { 'enabled': config_enabled[k] }
            else:
                config_enabled[k] = { 'enabled' : false }
            config_enabled[k]['display_name'] = config_display[k]
        config_idx = config_enabled

    system_indices_list = parseIndicesBySystemList(index_response, alliance_systems, config_idx)
    output_string = buildOutputString(system_indices_list, config_idx)

    # if the config file is true for slack
    if configuration['webhooks']['slack']:
        postSlackWebhook(output_string)

    # if the config file is true for discord
    if configuration['webhooks']['discord']:
        postDiscordWebhook(output_string)

    if 'verbose' in configuration and configuration['verbose']:
        print(output_string)


if __name__ == "__main__":
    # opens config file
    configFile = open("./config.json")

    # returns JSON object as a dictionary
    configuration = json.load(configFile)

    # Calls the function to fetch, and send, the indexes
    GetIndices(configuration["alliance_IDs"])
