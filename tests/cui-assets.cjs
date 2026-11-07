// Test-only access to the presentation packaged with this checkout.
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../cmail'),vendor=path.join(root,'static/vendor/cui');
const manifest=JSON.parse(fs.readFileSync(path.join(vendor,'cui.asset.json'),'utf8'));
module.exports={...fs,readFileSync(file,options){
 const alias=path.relative(root,file).replaceAll('\\','/'),name=manifest.resources[alias];
 return fs.readFileSync(name?path.join(vendor,manifest.release,name):file,options);
}};
