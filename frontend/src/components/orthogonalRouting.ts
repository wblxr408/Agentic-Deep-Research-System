import type {ArchitectureEdge,ArchitectureNode,ArchitectureScene} from './researchArchitecture'

type Point=[number,number]
type Side='left'|'right'|'top'|'bottom'
interface Rect {left:number;top:number;right:number;bottom:number;owner?:string}
interface Port {anchor:Point;point:Point;direction:number;preference:number}
export interface OrthogonalRoute {path:string;x:number;y:number;labelVisible:boolean}
const dimensions=(node:ArchitectureNode)=>({width:node.width||190,height:node.height||88})
const inside=(point:Point,box:Rect)=>point[0]>box.left&&point[0]<box.right&&point[1]>box.top&&point[1]<box.bottom
const intersects=(a:Point,b:Point,box:Rect)=>a[0]===b[0]
  ?a[0]>box.left&&a[0]<box.right&&Math.max(a[1],b[1])>box.top&&Math.min(a[1],b[1])<box.bottom
  :a[1]>box.top&&a[1]<box.bottom&&Math.max(a[0],b[0])>box.left&&Math.min(a[0],b[0])<box.right
const textWidth=(text:string,size:number)=>Array.from(text).reduce((width,char)=>width+(char.charCodeAt(0)>255?size:size*.56),0)
const simplify=(points:Point[])=>points.reduce<Point[]>((result,point)=>{
  const last=result[result.length-1],before=result[result.length-2]
  if(last&&last[0]===point[0]&&last[1]===point[1])return result
  if(before&&((before[0]===last[0]&&last[0]===point[0])||(before[1]===last[1]&&last[1]===point[1])))result.pop()
  result.push(point);return result
},[])

/** Scene-sized visibility grid. Routes share corridors, with a cost for overlap/crossing. */
export function orthogonalRoutes(scene:ArchitectureScene):OrthogonalRoute[] {
  const boxes:Rect[]=scene.nodes.map(node=>{const {width,height}=dimensions(node);return {left:node.x-10,top:node.y-10,right:node.x+width+10,bottom:node.y+height+10,owner:node.id}})
  for(const region of scene.regions){
    if(region.hideHeader)continue
    const labelWidth=Math.min(region.width-32,textWidth(region.title,14)+textWidth(region.subtitle,11)+20+(region.agentRole?48:0))
    boxes.push({left:region.x+12,top:region.y+8,right:region.x+18+labelWidth,bottom:region.y+(region.agentRole?56:38)})
  }
  const byId=new Map(scene.nodes.map(node=>[node.id,node]))
  const clear=(a:Point,b:Point,owner?:string)=>!boxes.some(box=>(owner===undefined||box.owner!==owner)&&intersects(a,b,box))
  const ports=(node:ArchitectureNode,other:ArchitectureNode,side?:Side,incoming=false):Port[]=>{
    const {width,height}=dimensions(node),dx=other.x-node.x,dy=other.y-node.y,horizontal=Math.abs(dx)>Math.abs(dy)
    const preferred:Side=horizontal?(dx>=0?'right':'left'):(dy>=0?'bottom':'top')
    const sides:Side[]=side?[side]:[preferred,...(['right','bottom','left','top'] as Side[]).filter(value=>value!==preferred)]
    return sides.flatMap((value,index)=>{
      const anchor:Point=[node.x+(value==='right'?width:value==='left'?0:width/2),node.y+(value==='bottom'?height:value==='top'?0:height/2)]
      // Keep the main east/down flow straight; returning traffic uses a separate port.
      if(value==='right'&&incoming)anchor[1]-=Math.min(14,height*.16)
      if(value==='left'&&!incoming)anchor[1]+=Math.min(14,height*.16)
      if(value==='bottom'&&incoming)anchor[0]-=14
      if(value==='top'&&!incoming)anchor[0]+=14
      const point:Point=[anchor[0]+(value==='right'?20:value==='left'?-20:0),anchor[1]+(value==='bottom'?20:value==='top'?-20:0)]
      return boxes.some(box=>inside(point,box))||!clear(anchor,point,node.id)?[]:[{anchor,point,direction:value==='left'||value==='right'?0:1,preference:index*22}]
    })
  }
  const candidates=scene.edges.map(edge=>{const a=byId.get(edge.from)!,b=byId.get(edge.to)!;return {start:ports(a,b,edge.fromSide),end:ports(b,a,edge.toSide,true)}})
  const xs=new Set<number>([8,scene.width-8]),ys=new Set<number>([8,scene.height-8])
  for(const box of boxes){xs.add(box.left-4);xs.add(box.right+4);ys.add(box.top-4);ys.add(box.bottom+4)}
  for(const pair of candidates)for(const port of [...pair.start,...pair.end]){xs.add(port.point[0]);ys.add(port.point[1])}
  for(const edge of scene.edges)for(const [x,y] of edge.via||[]){xs.add(x);ys.add(y)}
  const columns=[...xs].sort((a,b)=>a-b),rows=[...ys].sort((a,b)=>a-b),stride=columns.length
  const points:Point[]=rows.flatMap(y=>columns.map(x=>[x,y] as Point)),free=points.map(point=>!boxes.some(box=>inside(point,box)))
  const neighbors:Array<Array<{id:number;length:number;axis:number}>>=points.map(()=>[])
  for(let id=0;id<points.length;id++){
    if(!free[id])continue
    const row=Math.floor(id/stride),column=id%stride
    for(const target of [column+1<stride?id+1:-1,row+1<rows.length?id+stride:-1]){
      if(target<0||!free[target]||!clear(points[id],points[target]))continue
      const axis=points[id][1]===points[target][1]?0:1,length=Math.abs(points[id][0]-points[target][0])+Math.abs(points[id][1]-points[target][1])
      neighbors[id].push({id:target,length,axis});neighbors[target].push({id,length,axis})
    }
  }
  const gridId=(point:Point)=>rows.indexOf(point[1])*stride+columns.indexOf(point[0])
  const segmentUse=new Map<string,number>(),pointUse=new Map<number,Set<number>>()
  const segmentKey=(a:number,b:number)=>a<b?`${a}:${b}`:`${b}:${a}`
  const search=(starts:Port[],ends:Port[]):{points:Point[];grid:number[]}|undefined=>{
    if(!starts.length||!ends.length)return
    const targets=ends.map(port=>({id:gridId(port.point),port})),goals=new Map(targets.map(target=>[target.id,target.port]))
    const count=points.length*2,distance=new Float64Array(count).fill(Infinity),previous=new Int32Array(count).fill(-1)
    const origins=new Map<number,Port>(),queue:Array<{state:number;score:number}>=[]
    const push=(entry:{state:number;score:number})=>{let index=queue.length;queue.push(entry);while(index){const parent=(index-1)>>1;if(queue[parent].score<=entry.score)break;queue[index]=queue[parent];index=parent}queue[index]=entry}
    const pop=()=>{const first=queue[0],last=queue.pop()!;if(queue.length){let index=0;while(index*2+1<queue.length){let child=index*2+1;if(child+1<queue.length&&queue[child+1].score<queue[child].score)child++;if(queue[child].score>=last.score)break;queue[index]=queue[child];index=child}queue[index]=last}return first}
    const heuristic=(id:number)=>Math.min(...targets.map(target=>Math.abs(points[id][0]-points[target.id][0])+Math.abs(points[id][1]-points[target.id][1])+target.port.preference))
    for(const port of starts){const id=gridId(port.point),state=id*2+port.direction;if(id<0||!free[id])continue;distance[state]=20+port.preference;origins.set(state,port);push({state,score:distance[state]+heuristic(id)})}
    let found=-1,best=Infinity
    while(queue.length){
      const entry=pop(),id=Math.floor(entry.state/2),axis=entry.state%2
      if(entry.score>distance[entry.state]+heuristic(id)+.01)continue
      if(entry.score>=best)break
      const goal=goals.get(id)
      if(goal){const cost=distance[entry.state]+goal.preference+(axis===goal.direction?0:24);if(cost<best){best=cost;found=entry.state}}
      for(const next of neighbors[id]){
        const target=next.id*2+next.axis,used=segmentUse.get(segmentKey(id,next.id))||0,crossing=pointUse.get(next.id)
        const cost=distance[entry.state]+next.length+(axis===next.axis?0:24)+used*next.length*.7+(crossing?.has(1-next.axis)?50:0)
        if(cost>=distance[target])continue;distance[target]=cost;previous[target]=entry.state;push({state:target,score:cost+heuristic(next.id)})
      }
    }
    if(found<0)return
    const grid:number[]=[];let cursor=found
    while(previous[cursor]>=0){grid.push(Math.floor(cursor/2));cursor=previous[cursor]}
    grid.push(Math.floor(cursor/2));grid.reverse()
    const start=origins.get(cursor)!,end=goals.get(Math.floor(found/2))!
    return {points:[start.anchor,...grid.map(id=>points[id]),end.anchor],grid}
  }
  const output:OrthogonalRoute[]=scene.edges.map(()=>({path:'',x:0,y:0,labelVisible:false})),labels:Rect[]=[]
  const order=scene.edges.map((edge,index)=>({edge,index,rank:edge.kind==='control'?2:edge.kind==='return'?3:0})).sort((a,b)=>a.rank-b.rank||a.index-b.index)
  for(const {edge,index} of order){
    const pair=candidates[index]
    // Optional waypoints reserve outer return channels; blocked hints are omitted.
    const hints=(edge.via||[]).filter(point=>free[gridId(point)])
    let routed:Point[]=[],grid:number[]=[],starts=pair.start,valid=true
    for(let section=0;section<=hints.length;section++){
      const hint=hints[section],ends=hint?[{anchor:hint,point:hint,direction:0,preference:0},{anchor:hint,point:hint,direction:1,preference:0}]:pair.end
      const result=search(starts,ends)
      if(!result){valid=false;break}routed.push(...result.points);grid.push(...result.grid)
      if(hint)starts=[{anchor:hint,point:hint,direction:0,preference:0},{anchor:hint,point:hint,direction:1,preference:0}]
    }
    if(!valid){const result=search(pair.start,pair.end);routed=result?.points||[];grid=result?.grid||[]}
    const simplified=simplify(routed)
    for(let part=1;part<grid.length;part++){
      const a=grid[part-1],b=grid[part];if(a===b)continue
      const key=segmentKey(a,b);segmentUse.set(key,(segmentUse.get(key)||0)+1)
      const axis=points[a][1]===points[b][1]?0:1
      for(const id of [a,b]){const used=pointUse.get(id)||new Set<number>();used.add(axis);pointUse.set(id,used)}
    }
    const label=placeLabel(simplified,edge,boxes,labels)
    output[index]={path:simplified.map(([x,y],part)=>part?(simplified[part-1][1]===y?`H${x}`:`V${y}`):`M${x},${y}`).join(' '),...label}
  }
  return output
}
function placeLabel(points:Point[],edge:ArchitectureEdge,obstacles:Rect[],occupied:Rect[]) {
  if(!edge.label)return {x:0,y:0,labelVisible:false}
  const width=textWidth(edge.label,11)+12,segments=points.slice(1).map((point,index)=>({a:points[index],b:point,length:Math.abs(point[0]-points[index][0])+Math.abs(point[1]-points[index][1])})).sort((a,b)=>Number(b.a[1]===b.b[1])-Number(a.a[1]===a.b[1])||b.length-a.length)
  for(const segment of segments){
    const x=(segment.a[0]+segment.b[0])/2,y=(segment.a[1]+segment.b[1])/2
    for(const [cx,cy] of segment.a[1]===segment.b[1]?[[x,y-7],[x,y+18]]:[[x+width/2+8,y],[x-width/2-8,y]]){
      const box={left:cx-width/2,top:cy-13,right:cx+width/2,bottom:cy+3}
      if([...obstacles,...occupied].some(other=>box.left<other.right&&box.right>other.left&&box.top<other.bottom&&box.bottom>other.top))continue
      occupied.push(box);return {x:cx,y:cy,labelVisible:true}
    }
  }
  return {x:0,y:0,labelVisible:false}
}
