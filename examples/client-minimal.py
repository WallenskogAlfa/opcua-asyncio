import asyncio
import sys
import json
from asyncua import Client

url = "opc.tcp://127.0.0.1:4840"
namespace = "urn:B&R/pv/"


def createEntryList(valueTypeIdList, nodeList, nodeNameList):
    """
        Create list of dicts based on how the config file should look
        with all the relevant data 
        List of dicts is returned to write to json
    """
    writeList= []
    translationDict = {3: "UInt16", 6: "Int32", 10: "Float", 12: "String"}
    for i, typeId in enumerate(valueTypeIdList):
        #skip 22 since it means its a structure and not a variable
        if int(typeId) !=22: 
            nodeInfo = dict({'NodeId': '', 'Name': '', 'Type': '', 'Unit': None, 'Message': None, 'EventType': 0, 'TagRuleSet': None})
            nodeInfo["NodeId"] = nodeNameList[i]
            writeList.append(nodeInfo)
            writeList[i]["Name"] = nodeList[i]
            writeList[i]["Type"] = translationDict[int(typeId)]
    return writeList

async def getLists(childrenOfNode):
    """
        Create relevant lists based on the children of the node 
        list of DataValues are returned
    """
    async with Client(url=url):
        valueTypeIdList = []
        nameList = []
        nodeNameList = []
        for node in childrenOfNode:
            valueType = await node.read_data_type()
            valueTypeId = str(valueType).rsplit("=")[1]
            valueTypeId = valueTypeId.rsplit(",")[0]
            names = str(node).rsplit(".")[-1]
            nodename = str(node)
            nodeNameList.append(nodename)
            nameList.append(names)
            valueTypeIdList.append(valueTypeId)
            
        return valueTypeIdList, nameList, nodeNameList

async def main():

    print(f"Connecting to {url} ...")
    async with Client(url=url) as client:
        # Find the namespace index
        nsidx = await client.get_namespace_index(namespace)
        print(f"Namespace Index for '{namespace}': {nsidx}")

        nodesToGet = ["ns=6;s=::ALIOT:UNS.ShippingCompany",
                      "ns=6;s=::ALIOT:UNS.ShippingCompany.Vessel",
                      "ns=6;s=::ALIOT:UNS.ShippingCompany.Vessel.Section[0].Tank[0]",
                      "ns=6;s=::ALIOT:UNS.ShippingCompany.Vessel.Section[0].Tank[1]",
                      "ns=6;s=::ALIOT:UNS.ShippingCompany.Vessel.Section[0].Tank[2]",
                      "ns=6;s=::ALIOT:UNS.ShippingCompany.Vessel.Section[0].Tank[0].MachinePosition[0]",
                      "ns=6;s=::ALIOT:UNS.ShippingCompany.Vessel.Section[0].Tank[0].MachinePosition[1]",
                      "ns=6;s=::ALIOT:UNS.ShippingCompany.Vessel.Section[0].Tank[1].MachinePosition[0]",
                      "ns=6;s=::ALIOT:UNS.ShippingCompany.Vessel.Section[0].Tank[2].MachinePosition[0]"
                     ]

        filename= 'C:/Users/SELUNWAF/Documents/Scanjet_ict_1_0_0_ALIOT.json'
        allEntrys = []

        for i in range(len(nodesToGet)):
            valueTypeIdList= []
            nameList=[]
            nodeNameList=[]
            childrenOfNode = await  client.get_node(nodesToGet[i]).get_children()
            valueTypeIdList, nameList, nodeNameList = await getLists(childrenOfNode)
            entryList = createEntryList(valueTypeIdList, nameList, nodeNameList)
            allEntrys.extend(entryList)
        #write all entrys into the config file .json
        jsonDict = {"DriverTagSet": allEntrys}
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(json.dumps(jsonDict, indent=2))

        sys.exit()

       #new_value = value - 50
       #print(f"Setting value of MyVariable to {new_value} ...")
       #await var.write_value(new_value)

        # Calling a method
        res = await client.nodes.objects.call_method(f"{nsidx}:ServerMethod", 5)
        print(f"Calling ServerMethod returned {res}")


if __name__ == "__main__":
    asyncio.run(main())
