import java.nio.file.*;
import java.util.*;
import net.irisshaders.iris.shaderpack.include.*;
import net.irisshaders.iris.shaderpack.option.*;
import net.irisshaders.iris.shaderpack.parsing.*;

// Uses the installed Iris parser; this does not construct an in-game pipeline.
public class IrisMetadataCheck {
    public static void main(String[] args) throws Exception {
        Path root=Path.of(args[0]);
        var holder=new DispatchingDirectiveHolder();
        Set<String> seen=new HashSet<>();
        holder.acceptConstStringDirective("colortex12Format", value -> {
            if (!value.equals("RGBA16")) throw new AssertionError(value);
            seen.add("colortex12Format");
        });
        String config=Files.readString(root.resolve("lib/Config.glsl"));
        for (var directive:ConstDirectiveParser.findDirectives(config)) holder.processDirective(directive);
        if (!seen.contains("colortex12Format")) throw new AssertionError("Glass G-buffer format missing");
        Path handheld=root.resolve("program/prepare/ResolveHandheldPosition.comp");
        if(Files.exists(handheld)) {
            var compute=new net.irisshaders.iris.shaderpack.programs.ComputeSource("deferred18","",null,
                net.irisshaders.iris.shaderpack.properties.ShaderProperties.empty());
            for(var directive:ConstDirectiveParser.findDirectives(Files.readString(handheld))) {
                if(directive.getKey().equals("workGroups")) ComputeDirectiveParser.setComputeWorkGroups(compute,directive);
            }
            if(compute.getWorkGroups()==null || compute.getWorkGroups().x!=1 || compute.getWorkGroups().y!=1 || compute.getWorkGroups().z!=1)
                throw new AssertionError("Handheld dispatch must resolve to one 2-thread workgroup");
        }
        Set<String> references=new HashSet<>(); int files=0;
        try(var paths=Files.walk(root)) {
            for (Path p:paths.filter(Files::isRegularFile).toList()) {
                if (!p.toString().matches(".*\\.(glsl|csh|fsh|vsh|comp|frag|vert)$")) continue;
                var annotated=new OptionAnnotatedSource(Files.readString(p));
                references.addAll(annotated.getBooleanDefineReferences().keySet()); files++;
            }
        }
        var annotatedSettings=new OptionAnnotatedSource(Files.readString(root.resolve("lib/Setting.glsl")));
        var set=annotatedSettings.getOptionSet(AbsolutePackPath.fromAbsolutePath("/lib/Setting.glsl"),references);
        for(String name:List.of("RT_PHYSICAL_GLASS","RT_GLASS_ENABLED","RT_LOCAL_LIGHTS","RT_LOCAL_SOFT_SHADOWS","RT_LOCAL_ACCELERATION","RT_LOCAL_VOLUMETRICS","RT_LOCAL_HALF_RES","RT_BLOCK_CUSTOM_COLOR","HELD_LIGHT_CUSTOM_COLOR","RT_HANDHELD_FLASHLIGHT")) {
            if(!set.isBooleanOption(name)) throw new AssertionError("Missing boolean "+name);
        }
        for(String name:List.of("RT_GLASS_ROUGHNESS","RT_LOCAL_SHADOW_SAMPLES","RT_HANDHELD_RADIUS","RT_LOCAL_SOURCE_SIZE","RT_LOCAL_HAZE_DENSITY","RT_LOCAL_VOLUME_SAMPLES","HELD_LIGHT_COLOR_R","HELD_LIGHT_COLOR_G","HELD_LIGHT_COLOR_B","RT_FLASHLIGHT_FOV","RT_FLASHLIGHT_SOFTNESS","RT_FLASHLIGHT_RANGE","BLOCKLIGHT_BRIGHTNESS","HELD_LIGHT_BRIGHTNESS")) {
            if(!set.getStringOptions().containsKey(name)) throw new AssertionError("Missing value "+name);
        }
        var builder=OptionSet.builder();
        try(var paths=Files.walk(root)) {
            for(Path p:paths.filter(Files::isRegularFile).toList()) {
                if(!p.toString().matches(".*\\.(glsl|csh|fsh|vsh|comp|frag|vert)$")) continue;
                var annotated=new OptionAnnotatedSource(Files.readString(p));
                builder.addAll(annotated.getOptionSet(AbsolutePackPath.fromAbsolutePath("/"+root.relativize(p).toString().replace('\\','/')),references));
            }
        }
        var allOptions=builder.build();
        Map<String,List<String>> tree=new LinkedHashMap<>();
        String properties=Files.readString(root.resolve("shaders.properties"));
        for(String line:properties.split("\\R")) if(line.startsWith("profile.")) {
            String[] parts=line.split("=",2);
            tree.put(parts[0].trim().substring(8),List.of(parts[1].trim().split("\\s+")));
        }
        if(!tree.keySet().equals(new LinkedHashSet<>(List.of("Default","Low","Medium","High","Ultra","RayTracing")))) throw new AssertionError("Six quality levels missing: "+tree.keySet());
        var profiles=ProfileSet.fromTree(tree,allOptions);
        if(profiles.size()!=6) throw new AssertionError("Profile parsing failed");
        Map<String,Profile> parsed=new LinkedHashMap<>();
        profiles.forEach(parsed::put);
        for(var entry:parsed.entrySet()) {
            Profile profile=entry.getValue();
            for(String personal:List.of("RT_BLOCK_CUSTOM_COLOR","HELD_LIGHT_CUSTOM_COLOR","RT_HANDHELD_FLASHLIGHT","HELD_LIGHT_COLOR_R","HELD_LIGHT_COLOR_G","HELD_LIGHT_COLOR_B","BLOCKLIGHT_COLOR_R","BLOCKLIGHT_COLOR_G","BLOCKLIGHT_COLOR_B","RT_FLASHLIGHT_FOV","RT_FLASHLIGHT_SOFTNESS","RT_FLASHLIGHT_RANGE","BLOCKLIGHT_BRIGHTNESS","HELD_LIGHT_BRIGHTNESS")) {
                if(profile.optionValues.containsKey(personal)) throw new AssertionError("Quality profile resets user light setting: "+personal);
            }
            if(profile.optionValues.size()!=tree.get(entry.getKey()).size()) throw new AssertionError("Dropped option in "+entry.getKey()+": "+profile.optionValues.size());
            for(var option:profile.optionValues.entrySet()) {
                var string=allOptions.getStringOptions().get(option.getKey());
                if(string!=null && !string.getOption().getAllowedValues().contains(option.getValue())) throw new AssertionError("Invalid "+option);
            }
            var values=new net.irisshaders.iris.shaderpack.option.values.MutableOptionValues(allOptions,profile.optionValues);
            var result=profiles.scan(allOptions,values);
            if(result.current.isEmpty() || !result.current.get().name.equals(profile.name)) throw new AssertionError("Ambiguous selector "+profile.name);
            for(Profile previous:parsed.values()) {
                var switched=new net.irisshaders.iris.shaderpack.option.values.MutableOptionValues(allOptions,previous.optionValues);
                switched.addAll(profile.optionValues);
                if(!profile.matches(allOptions,switched)) throw new AssertionError("Cannot switch "+previous.name+" -> "+profile.name);
            }
        }
        var defaults=new net.irisshaders.iris.shaderpack.option.values.MutableOptionValues(allOptions,Map.of());
        if(!parsed.get("Ultra").matches(allOptions,defaults)) throw new AssertionError("Initial shader defaults must match Ultra quality");
        String screen=properties.substring(properties.indexOf("screen ="),properties.indexOf("screen.Environment"));
        if(!screen.contains("<profile>")) throw new AssertionError("Root profile selector missing");
        if(!screen.contains("[LightSources]")) throw new AssertionError("Light controls not exposed on main screen");
        for(String page:List.of("BlockLightSettings","HandheldLightSettings","FlashlightSettings")) {
            if(!properties.contains("["+page+"]") || !properties.contains("screen."+page+" =")) throw new AssertionError("Light settings page missing: "+page);
        }
        Map<String,String> itemIds=new HashMap<>();
        for(String line:Files.readString(root.resolve("item.properties")).split("\\R")) {
            if(!line.startsWith("item.")) continue;
            String[] pair=line.split("=",2);
            for(String item:pair[1].trim().split("\\s+")) {
                if(itemIds.put(item,pair[0].substring(5))!=null) throw new AssertionError("Duplicate item mapping: "+item);
            }
        }
        if(!"10005".equals(itemIds.get("minecraft:torch")) || !"10006".equals(itemIds.get("minecraft:soul_torch")) || !"10007".equals(itemIds.get("minecraft:redstone_torch")) || !"10001".equals(itemIds.get("minecraft:lantern"))) throw new AssertionError("Torch-only flashlight item mapping");
        System.out.println("PASS: installed Iris 1.8.14-beta.1 metadata; "+files+" sources; six quality profiles, 36 transitions, matching Ultra defaults; independent light-control pages and torch-only flashlight options; RGBA16 glass buffer");
    }
}
