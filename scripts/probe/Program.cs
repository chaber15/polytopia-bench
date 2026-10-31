using System.Collections.Immutable;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
// usage: probe <dir> <dllname> <substring> [type-to-dump-members [method-filter]]
var f = Path.Combine(args[0], args[1]);
using var pe = new PEReader(File.OpenRead(f));
var md = pe.GetMetadataReader();
var prov = new Prov(md);
foreach (var h in md.TypeDefinitions) {
  var t = md.GetTypeDefinition(h); var n = md.GetString(t.Name);
  if (args.Length > 3) {
    if (n != args[3]) continue;
    var filt = args.Length > 4 ? args[4] : "";
    foreach (var mh in t.GetMethods()) {
      var m = md.GetMethodDefinition(mh); var mn = md.GetString(m.Name);
      if (filt != "" && !mn.Contains(filt, StringComparison.OrdinalIgnoreCase)) continue;
      string sig;
      try {
        var s = m.DecodeSignature(prov, null);
        var names = m.GetParameters().Select(p => md.GetParameter(p)).Where(p => p.SequenceNumber > 0).OrderBy(p => p.SequenceNumber).Select(p => md.GetString(p.Name)).ToList();
        sig = string.Join(", ", s.ParameterTypes.Select((pt, i) => pt + " " + (i < names.Count ? names[i] : "")));
        sig = $"{s.ReturnType} {mn}({sig})";
      } catch (Exception e) { sig = mn + " <" + e.Message + ">"; }
      Console.WriteLine("  m " + ((m.Attributes & System.Reflection.MethodAttributes.Static) != 0 ? "static " : "") + sig);
    }
    if (filt == "") {
      foreach (var ph in t.GetProperties()) Console.WriteLine("  p " + md.GetString(md.GetPropertyDefinition(ph).Name));
      foreach (var fh in t.GetFields()) { var fd = md.GetFieldDefinition(fh); string ft; try { ft = fd.DecodeSignature(prov, null); } catch { ft = "?"; } Console.WriteLine("  f " + ft + " " + md.GetString(fd.Name)); }
    }
    var bt = t.BaseType; if (!bt.IsNil && bt.Kind == HandleKind.TypeReference) Console.WriteLine("  base " + md.GetString(md.GetTypeReference((TypeReferenceHandle)bt).Name));
    else if (!bt.IsNil && bt.Kind == HandleKind.TypeDefinition) Console.WriteLine("  base " + md.GetString(md.GetTypeDefinition((TypeDefinitionHandle)bt).Name));
  } else if (n.Contains(args[2])) Console.WriteLine($"{md.GetString(t.Namespace)}.{n}");
}
class Prov : ISignatureTypeProvider<string, object?> {
  readonly MetadataReader md; public Prov(MetadataReader m) { md = m; }
  public string GetArrayType(string e, ArrayShape s) => e + "[,]";
  public string GetByReferenceType(string e) => "ref " + e;
  public string GetFunctionPointerType(MethodSignature<string> s) => "fnptr";
  public string GetGenericInstantiation(string g, ImmutableArray<string> a) => g + "<" + string.Join(",", a) + ">";
  public string GetGenericMethodParameter(object? c, int i) => "!!" + i;
  public string GetGenericTypeParameter(object? c, int i) => "!" + i;
  public string GetModifiedType(string m, string u, bool r) => u;
  public string GetPinnedType(string e) => e;
  public string GetPointerType(string e) => e + "*";
  public string GetPrimitiveType(PrimitiveTypeCode t) => t.ToString();
  public string GetSZArrayType(string e) => e + "[]";
  public string GetTypeFromDefinition(MetadataReader r, TypeDefinitionHandle h, byte k) => r.GetString(r.GetTypeDefinition(h).Name);
  public string GetTypeFromReference(MetadataReader r, TypeReferenceHandle h, byte k) => r.GetString(r.GetTypeReference(h).Name);
  public string GetTypeFromSpecification(MetadataReader r, object? c, TypeSpecificationHandle h, byte k) => "spec";
}
