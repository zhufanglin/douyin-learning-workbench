import { Button } from '@/components/ui/button'
export type FieldDraft = {name:string;terms:string}
export function FieldConfig({value,onChange,disabled}:{value:FieldDraft[];onChange:(value:FieldDraft[])=>void;disabled:boolean}) {
 return <fieldset className="space-y-3 border rounded-xl p-3" disabled={disabled}><legend>需求字段（可选）</legend>
 <p className="text-xs">添加自己的字段名和匹配短语，每行一个短语。只记录原文提及，未命中留空；每个业务最多10个字段，每个字段最多50个短语。</p>
 {value.map((field,i)=><div key={i} className="space-y-2 border-t pt-2"><label className="block text-sm">字段名称<input className="library-select w-full" aria-label={'字段名称 '+(i+1)} maxLength={40} value={field.name} onChange={e=>onChange(value.map((v,j)=>j===i?{...v,name:e.target.value}:v))}/></label><label className="block text-sm">匹配短语<textarea className="library-select w-full" aria-label={'字段短语 '+(i+1)} rows={2} maxLength={4000} value={field.terms} onChange={e=>onChange(value.map((v,j)=>j===i?{...v,terms:e.target.value}:v))}/></label><Button size="sm" variant="ghost" onClick={()=>onChange(value.filter((_,j)=>j!==i))}>移除此字段</Button></div>)}
 <Button size="sm" variant="outline" disabled={disabled||value.length>=10} onClick={()=>onChange([...value,{name:'',terms:''}])}>添加需求字段</Button>
 </fieldset>
}
