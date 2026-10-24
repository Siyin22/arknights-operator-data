using Mono.Cecil;
using System.Text.Json;

object Value(CustomAttributeArgument a) => a.Value is TypeReference t ? t.FullName : a.Value;
object[] Attrs(ICustomAttributeProvider x) => x.CustomAttributes
    .Where(a => a.AttributeType.Namespace == "Newtonsoft.Json" || a.AttributeType.Name == "NonSerializedAttribute")
    .Select(a => (object)new {name=a.AttributeType.FullName, args=a.ConstructorArguments.Select(Value).ToArray(),
        fields=a.Fields.ToDictionary(f=>f.Name,f=>Value(f.Argument)),
        properties=a.Properties.ToDictionary(f=>f.Name,f=>Value(f.Argument))}).ToArray();
string Mark(ICustomAttributeProvider x, string attr, string field) => x.CustomAttributes
    .FirstOrDefault(a=>a.AttributeType.Name==attr)?.Fields.FirstOrDefault(f=>f.Name==field).Argument.Value?.ToString();
IEnumerable<TypeDefinition> Walk(TypeDefinition t) { yield return t; foreach(var n in t.NestedTypes) foreach(var v in Walk(n)) yield return v; }
var results = new List<object>();
var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetFullPath(args[0]));
foreach(var file in Directory.GetFiles(args[0], "*.dll")) {
    using var asm = AssemblyDefinition.ReadAssembly(file, new ReaderParameters {AssemblyResolver=resolver});
    foreach(var t in asm.MainModule.Types.SelectMany(Walk)) {
        results.Add(new {name=t.FullName, kind=t.IsEnum?"enum":t.IsValueType?"struct":"class",
            parent=t.BaseType?.FullName, generic=t.GenericParameters.Select(g=>g.Name).ToArray(), attrs=Attrs(t),
            fields=t.Fields.Select(f=>new {name=f.Name,type=f.FieldType.FullName, isPublic=f.IsPublic,
                isStatic=f.IsStatic, constant=f.HasConstant?f.Constant:null,offset=Mark(f,"FieldOffsetAttribute","Offset"),attrs=Attrs(f)}).ToArray(),
            properties=t.Properties.Select(p=>new {name=p.Name,type=p.PropertyType.FullName,attrs=Attrs(p)}).ToArray(),
            methods=t.Methods.Where(m=>m.Name.StartsWith("Unpack") || t.Name.Contains("FlatBuffer") || t.Name=="Table")
                .Select(m=>new {name=m.Name,rva=Mark(m,"AddressAttribute","RVA"),signature=m.FullName}).ToArray()
        });
    }
}
File.WriteAllText(args[1],JsonSerializer.Serialize(results, new JsonSerializerOptions {NumberHandling=System.Text.Json.Serialization.JsonNumberHandling.AllowNamedFloatingPointLiterals}));
Console.WriteLine($"Exported {results.Count} type definitions");
