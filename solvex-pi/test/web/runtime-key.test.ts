import { it, expect, vi } from 'vitest';
import { createServer } from '@solvex/web';
import { ModelRuntimeManager } from '@solvex/pi-runtime';
import { readFileSync } from 'node:fs';
import { testPaths } from './helpers.js';
it('a key entered in the WebUI authenticates the runner runtime without appearing in the model response', async () => {
  const paths = testPaths();
  const keys = new Map<string,string>();
  let catalog: any = {};
  const rt = { getAvailable: async()=>[], getModel:(p:string,id:string)=>catalog.providers?.[p]?.models.find((m:any)=>m.id===id),
    setRuntimeApiKey: async(p:string,k:string)=>{keys.set(p,k);}, refresh:async()=>{catalog=JSON.parse(readFileSync(paths.modelsPath,'utf8'));},
    listCredentials:async()=>[], getRegisteredProviderIds:()=>[] };
  const manager = await ModelRuntimeManager.create({sdkRuntime:rt});
  const shared = vi.spyOn(ModelRuntimeManager,'shared').mockResolvedValue(manager);
  const app = await createServer({...paths});
  try {
    const res = await app.inject({method:'POST',url:'/api/models/api-key',payload:{provider:'anthropic',apiKey:'sk-test-runtime-key'}});
    expect(res.statusCode).toBe(200);
    expect(keys.get('anthropic')).toBe('sk-test-runtime-key');
    expect((await app.inject('/api/models')).body).not.toContain('sk-test-runtime-key');
    const endpoint = await app.inject({method:'PUT',url:'/api/models/endpoints',payload:{id:'custom',baseUrl:'https://example.com/v1',api:'openai-completions',apiKey:'$CUSTOM_KEY',models:['test-model']}});
    expect(endpoint.statusCode).toBe(200);
    expect(manager.resolve('custom','test-model')).toMatchObject({id:'test-model'});
  } finally {await app.close();shared.mockRestore();}
});
