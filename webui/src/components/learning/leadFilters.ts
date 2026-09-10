export function commentTimestamp(value?:string|number) {
 if(value===undefined||value===null||value==='')return null
 const raw=/^\d+$/.test(String(value))?Number(value):value
 const stamp=new Date(typeof raw==='number'&&raw<1e12?raw*1000:raw).getTime()
 return Number.isNaN(stamp)?null:stamp
}
export function matchesCommentDate(value:string|number|undefined,start:string,end:string,mode:string) {
 const stamp=commentTimestamp(value)
 if(mode==='missing')return stamp===null
 if(stamp===null)return mode!=='known'&&!start&&!end
 if(start&&stamp<new Date(start+'T00:00:00').getTime())return false
 if(end){const next=new Date(end+'T00:00:00');next.setDate(next.getDate()+1);if(stamp>=next.getTime())return false}
 return true
}
