from typing import Dict, Any, List, Optional
from print_etl_d.config import FieldDefinition
import google.generativeai as genai

def build_json_schema(fields: Dict[str, FieldDefinition]) -> Dict[str, Any]:
    """
    Convert config field definitions to a JSON schema for Gemini API.
    """
    properties = {}
    required_fields = []

    for name, field_def in fields.items():
        field_schema = _map_field_to_schema(field_def)
        properties[name] = field_schema
        required_fields.append(name)

    schema = {
        "type": "OBJECT",
        "properties": properties,
        "required": required_fields
    }
    
    return schema

def _map_field_to_schema(field_def: FieldDefinition) -> Dict[str, Any]:
    """Map a FieldDefinition to a JSON schema dict."""
    type_str = field_def.type.lower().strip()
    description = field_def.description

    # Handle explicit object type
    if type_str == "object":
        if not field_def.properties:
            # Generic object if no properties defined (though Gemini might prefer structure)
            return {"type": "OBJECT", "description": description}
        
        props = {}
        reqs = []
        for prop_name, prop_def in field_def.properties.items():
            props[prop_name] = _map_field_to_schema(prop_def)
            reqs.append(prop_name)
            
        return {
            "type": "OBJECT",
            "description": description,
            "properties": props,
            "required": reqs
        }

    # Handle explicit list with structural definition
    if type_str == "list" or type_str == "array":
        item_schema = {}
        if field_def.items:
            item_schema = _map_field_to_schema(field_def.items)
        else:
            # Fallback for generic list
            item_schema = {"type": "STRING"}
            
        return {
            "type": "ARRAY",
            "description": description,
            "items": item_schema
        }

    # Legacy syntax support: list[string], list[object], etc.
    if type_str.startswith("list[") and type_str.endswith("]"):
        inner_type = type_str[5:-1]
        
        # Special case: list[object] with defined properties in parent's 'items'
        if inner_type == "object" and field_def.items:
             return {
                "type": "ARRAY",
                "description": description,
                "items": _map_field_to_schema(field_def.items)
            }
            
        return {
            "type": "ARRAY",
            "description": description,
            "items": _map_simple_type(inner_type, "")
        }

    # Simple types
    return _map_simple_type(type_str, description)

def _map_simple_type(type_str: str, description: str) -> Dict[str, Any]:
    """Helper for simple types without nested structure."""
    if type_str == "string":
        return {"type": "STRING", "description": description}
    elif type_str in ("integer", "int"):
        return {"type": "INTEGER", "description": description}
    elif type_str in ("number", "float"):
        return {"type": "NUMBER", "description": description}
    elif type_str in ("boolean", "bool"):
        return {"type": "BOOLEAN", "description": description}
    else:
        return {"type": "STRING", "description": description}