"""
Generate address space code from xml file specification
xmlparser.py is a requirement.
It is in asyncua folder, but to avoid importing all code, developer can link xmlparser.py in current directory
"""
import asyncio
import sys
import datetime
import logging
from dataclasses import fields
# sys.path.insert(0, "..")  # load local freeopcua implementation
from pathlib import Path

from asyncua.common import xmlparser
from asyncua.ua.uatypes import type_string_from_type

BASE_DIR = Path.cwd().parent


def _to_val(objs, attr, val):
    from asyncua import ua
    cls = getattr(ua, objs[0])
    for o in objs[1:]:
        cls = getattr(ua, _get_uatype_name(cls, o))
    if cls == ua.NodeId:
        return f"NodeId.from_string('{val}')"
    return ua_type_to_python(val, _get_uatype_name(cls, attr))


def _get_uatype_name(cls, attname):
    for field in fields(cls):
        if field.name == attname:
            return type_string_from_type(field.type)
    raise Exception(f"Could not find attribute {attname} in obj {cls}")


def ua_type_to_python(val, uatype):
    if uatype == "String":
        return f"'{val}'"
    elif uatype in ("Bytes", "Bytes", "ByteString", "ByteArray"):
        return f"b'{val}'"
    else:
        return val


def bname_code(string):
    if ":" in string:
        idx, name = string.split(":", 1)
    else:
        idx = 0
        name = string
    return f"QualifiedName(\"{name}\", {idx})"


def nodeid_code(string):
    line = string.split(";")
    identifier = None
    namespace = 0
    ntype = None
    srv_set = False
    srv_idx = None
    for el in line:
        if not el:
            continue
        k, v = el.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k == "ns":
            namespace = v
        elif k == "i":
            ntype = "NumericNodeId"
            identifier = v
        elif k == "s":
            ntype = "StringNodeId"
            identifier = f"'{v}'"
        elif k == "g":
            ntype = "GuidNodeId"
            identifier = f"b'{v}'"
        elif k == "b":
            ntype = "ByteStringNodeId"
            identifier = f"b'{v}'"
        elif k == "srv":
            srv_idx = v
            srv_set = True
        elif k == "nsu":
            namespace = v
    if identifier is None:
        raise Exception("Could not find identifier in string: " + string)
    if srv_set:
        return f"{ntype}({identifier}, {namespace}, {srv_idx})"
    return f"{ntype}({identifier}, {namespace})"


class CodeGenerator:

    def __init__(self, input_path, output_path):
        self.input_path = input_path
        self.output_path = output_path
        self.output_file = None
        self.part = self.input_path.parts[-1].split(".")[-2]
        self.parser = None

    async def run(self):
        sys.stderr.write(f"Generating Python code {self.output_path} for XML file {self.input_path}\n")
        self.output_file = open(self.output_path, 'w', encoding='utf-8')
        self.make_header()
        self.parser = xmlparser.XMLParser()
        self.parser.parse_sync(self.input_path)
        for node in self.parser.get_node_datas():
            if node.nodetype == 'UAObject':
                self.make_object_code(node)
            elif node.nodetype == 'UAObjectType':
                self.make_object_type_code(node)
            elif node.nodetype == 'UAVariable':
                self.make_variable_code(node)
            elif node.nodetype == 'UAVariableType':
                self.make_variable_type_code(node)
            elif node.nodetype == 'UAReferenceType':
                self.make_reference_code(node)
            elif node.nodetype == 'UADataType':
                self.make_datatype_code(node)
            elif node.nodetype == 'UAMethod':
                self.make_method_code(node)
            else:
                sys.stderr.write(f"Not implemented node type: {node.nodetype}\n")
        self.output_file.close()

    def writecode(self, *args):
        self.output_file.write(f'{" ".join(args)}\n')

    def make_header(self, ):
        tree = xmlparser.ET.parse(self.input_path)
        model = ""
        for child in tree.iter():
            if child.tag.endswith("Model"):
                # check if ModelUri X, in Version Y from time Z was already imported
                model = child
                break

        self.writecode(
            f'''# -*- coding: utf-8 -*-\n'''
            f'''"""\n'''
            f'''DO NOT EDIT THIS FILE!\n'''
            f'''It is automatically generated from opcfoundation.org schemas.\n'''
            f''''''
            f'''Model Uri:{model.attrib["ModelUri"]}\n'''
            f'''Version:{model.attrib["Version"]}\n'''
            f'''Publication date:{model.attrib["PublicationDate"]}\n'''
            f'''\n'''
            f'''File creation Date:{datetime.datetime.utcnow()}\n'''
            f'''"""\n'''
            f'''import datetime\n'''
            f'''from dateutil.tz import tzutc\n'''
            f''''''
            f'''from asyncua import ua\n'''
            f'''from asyncua.ua import NodeId, QualifiedName, NumericNodeId, StringNodeId, GuidNodeId\n'''
            f'''from asyncua.ua import NodeClass, LocalizedText\n'''
            f'''\n'''
            f'''\n'''
            f'''def create_standard_address_space_{self.part!s}(server):''')

    def make_node_code(self, obj, indent):
        self.writecode(
            f'''    node = ua.AddNodesItem(\n'''
            f'''        RequestedNewNodeId={nodeid_code(obj.nodeid)},\n'''
            f'''        BrowseName={bname_code(obj.browsename)},\n'''
            f'''        NodeClass_=NodeClass.{obj.nodetype[2:]},'''
            )
        if obj.parent and obj.parentlink:
            self.writecode(
                f'''        ParentNodeId={nodeid_code(obj.parent)},\n'''
                f'''        ReferenceTypeId={self.to_ref_type(obj.parentlink)},''')
        if obj.typedef:
            self.writecode(indent, '    TypeDefinition={},'.format(nodeid_code(obj.typedef)))
        self.writecode(
            '        NodeAttributes=attrs,\n'
            '    )\n'
            f'    server.add_nodes([node])')

    @staticmethod
    def to_data_type(nodeid):
        if not nodeid:
            return "ua.NodeId(ua.ObjectIds.String)"
        if "=" in nodeid:
            return nodeid_code(nodeid)
        else:
            return f'ua.NodeId(ua.ObjectIds.{nodeid})'

    def to_ref_type(self, nodeid):
        if "=" not in nodeid:
            nodeid = self.parser.get_aliases()[nodeid]
        return nodeid_code(nodeid)

    def make_object_code(self, obj):
        indent = "   "
        self.writecode()
        self.writecode(indent, 'attrs = ua.ObjectAttributes(')
        if obj.desc:
            self.writecode(indent, '    Description=LocalizedText("""{0}"""),'.format(obj.desc))
        self.writecode(
            f'''        DisplayName=LocalizedText("{obj.displayname}"),\n'''
            f'''        EventNotifier={obj.eventnotifier},\n'''
            f'''        )'''
            )
        self.make_node_code(obj, indent)
        self.make_refs_code(obj, indent)

    def make_object_type_code(self, obj):
        indent = "   "
        self.writecode()
        self.writecode(indent, 'attrs = ua.ObjectTypeAttributes(')
        if obj.desc:
            self.writecode(indent, '   Description=LocalizedText("{0}"),'.format(obj.desc))
        self.writecode(
            f'''        DisplayName=LocalizedText("{obj.displayname}"),\n'''
            f'''        IsAbstract={obj.abstract},\n'''
            '''        )'''
            )
        self.make_node_code(obj, indent)
        self.make_refs_code(obj, indent)

    def make_common_variable_code(self, indent, obj):
        if obj.desc:
            self.writecode(indent, '    Description=LocalizedText("{0}"),'.format(obj.desc))
        self.writecode(indent, '    DisplayName=LocalizedText("{0}"),'.format(obj.displayname))
        self.writecode(indent, '    DataType={0},'.format(self.to_data_type(obj.datatype)))
        if obj.value is not None:
            if obj.valuetype == "ListOfExtensionObject":
                self.writecode(indent, '    Value=ua.Variant([')
                for ext in obj.value:
                    self.make_ext_obj_code(indent + "        ", ext)
                self.writecode(indent, '        ],')
                self.writecode(indent, '        ua.VariantType.ExtensionObject),')
            elif obj.valuetype == "ExtensionObject":
                self.writecode(indent, '    Value=ua.Variant(')
                self.make_ext_obj_code(indent + "    ", obj.value)
                self.writecode(indent, '    ua.VariantType.ExtensionObject),')
            elif obj.valuetype == "ListOfLocalizedText":
                value = ['LocalizedText({0})'.format(repr(d['Text'])) for d in obj.value]
                self.writecode(indent, '    Value=[{}],'.format(', '.join(value)))
            elif obj.valuetype == "LocalizedText":
                self.writecode(indent, '    Value=ua.Variant(LocalizedText("{0}"),'
                                       ' ua.VariantType.LocalizedText),'.format(obj.value[1][1]))
            else:
                if obj.valuetype.startswith("ListOf"):
                    obj.valuetype = obj.valuetype[6:]
                self.writecode(
                    indent,
                    f'    Value=ua.Variant({obj.value!r}, ua.VariantType.{obj.valuetype}),'
                )
        if obj.rank:
            self.writecode(indent, f'    ValueRank={obj.rank},')
        if obj.accesslevel:
            self.writecode(indent, f'    AccessLevel={obj.accesslevel},')
        if obj.useraccesslevel:
            self.writecode(indent, f'    UserAccessLevel={obj.useraccesslevel},')
        if obj.dimensions:
            self.writecode(indent, f'    ArrayDimensions={obj.dimensions},')
        self.writecode(indent, '    )')

    def make_ext_obj_code(self, indent, extobj, prefix=""):
        self.writecode(indent, f'{prefix}ua.{extobj.objname}(')
        for name, val in extobj.body:
            for k, v in val:
                if type(v) is str:
                    val = _to_val([extobj.objname], k, v)
                    self.writecode(indent, f'    {k}={val},')
                else:
                    if k == "DataType":  # hack for strange nodeid xml format
                        self.writecode(indent, '    {0}={1},'.format(k, nodeid_code(v[0][1])))
                        continue
                    if k == "ArrayDimensions":  # hack for v1.04 - Ignore UInt32 tag?
                        self.writecode(indent, '    ArrayDimensions=[{0}],'.format(v[0][1]))
                        continue
                    # hack for Locale
                    dic = { k2: _to_val([extobj.objname, k], k2, v2)  for k2, v2 in v}
                    text = dic.get("Text", "''")
                    locale = dic.get("Locale", None)
                    self.writecode(indent, f'    {k}=LocalizedText(Text={text}, Locale={locale}),')
        self.writecode(indent, '    ),')

    def make_variable_code(self, obj):
        indent = "   "
        self.writecode()
        self.writecode(indent, 'attrs = ua.VariableAttributes(')
        if obj.minsample:
            self.writecode(indent, f'    MinimumSamplingInterval={obj.minsample},')
        self.make_common_variable_code(indent, obj)
        self.make_node_code(obj, indent)
        self.make_refs_code(obj, indent)

    def make_variable_type_code(self, obj):
        indent = "   "
        self.writecode()
        self.writecode(indent, 'attrs = ua.VariableTypeAttributes(')
        if obj.desc:
            self.writecode(indent, '   Description=LocalizedText("{0}"),'.format(obj.desc))
        if obj.abstract:
            self.writecode(indent, f'    IsAbstract={obj.abstract},')
        self.make_common_variable_code(indent, obj)
        self.make_node_code(obj, indent)
        self.make_refs_code(obj, indent)

    def make_method_code(self, obj):
        indent = "   "
        self.writecode()
        self.writecode(indent, 'attrs = ua.MethodAttributes(')
        if obj.desc:
            self.writecode(indent, '    Description=LocalizedText("{0}"),'.format(obj.desc))
        self.writecode(
            f'        DisplayName=LocalizedText("{obj.displayname}"),\n'
            '    )')
        self.make_node_code(obj, indent)
        self.make_refs_code(obj, indent)

    def make_reference_code(self, obj):
        indent = "   "
        self.writecode()
        self.writecode(indent, 'attrs = ua.ReferenceTypeAttributes(')
        if obj.desc:
            self.writecode(indent, '    Description=LocalizedText("{0}"),'.format(obj.desc))
        self.writecode(indent, '    DisplayName=LocalizedText("{0}"),'.format(obj.displayname))
        if obj.inversename:
            self.writecode(indent, '    InverseName=LocalizedText("{0}"),'.format(obj.inversename))
        if obj.abstract:
            self.writecode(indent, f'    IsAbstract={obj.abstract},')
        if obj.symmetric:
            self.writecode(indent, f'    Symmetric={obj.symmetric},')
        self.writecode(indent, '    )')
        self.make_node_code(obj, indent)
        self.make_refs_code(obj, indent)

    def make_datatype_code(self, obj):
        indent = "   "
        self.writecode()
        self.writecode(indent, 'attrs = ua.DataTypeAttributes(')
        if obj.desc:
            self.writecode(indent, u'    Description=LocalizedText("{0}"),'.format(obj.desc))
        self.writecode(indent, '    DisplayName=LocalizedText("{0}"),'.format(obj.displayname))
        self.writecode(indent, f'    IsAbstract={obj.abstract},')
        self.writecode(indent, '    )')
        self.make_node_code(obj, indent)
        self.make_refs_code(obj, indent)

    def make_refs_code(self, obj, indent):
        if not obj.refs:
            return
        self.writecode(indent, "refs = []")
        for ref in obj.refs:
            self.writecode(
                f'''    ref = ua.AddReferencesItem(\n'''
                f'''        IsForward={ref.forward},\n'''
                f'''        ReferenceTypeId={self.to_ref_type(ref.reftype)},\n'''
                f'''        SourceNodeId={nodeid_code(obj.nodeid)},\n'''
                f'''        TargetNodeClass=NodeClass.DataType,\n'''
                f'''        TargetNodeId={nodeid_code(ref.target)},\n'''
                f'''        )\n'''
                f'''    refs.append(ref)''')
        self.writecode(indent, 'server.add_references(refs)')


def save_aspace_to_disk():
    path = BASE_DIR / 'asyncua' / 'binary_address_space.pickle'
    print('Saving standard address space to:', path)
    sys.path.append('..')
    from asyncua.server.standard_address_space import standard_address_space
    from asyncua.server.address_space import NodeManagementService, AddressSpace
    a_space = AddressSpace()
    standard_address_space.fill_address_space(NodeManagementService(a_space))
    a_space.dump(path)


async def main():
    logging.basicConfig(level=logging.WARN)
    xml_path = BASE_DIR / 'schemas' / 'UA-Nodeset-master' / 'Schema' / f'Opc.Ua.NodeSet2.Services.xml'
    py_path = BASE_DIR / 'asyncua' / 'server' / 'standard_address_space' / 'standard_address_space_services.py'
    await CodeGenerator(xml_path, py_path).run()
    save_aspace_to_disk()


if __name__ == '__main__':
    asyncio.run(main())
