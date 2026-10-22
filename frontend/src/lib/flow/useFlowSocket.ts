import { useEffect, useState } from 'react';
import { io } from 'socket.io-client';
import { flowStore, useFlowStore } from './useFlowStore';
import type { Market } from '../market';
import type { StreamStatus } from './flowTypes';

// One hook owns the terminal connection and releases it on selection/unmount.
export function useFlowSocket(symbol:string,market:Market='spot') {
 const [connection,setConnection]=useState<StreamStatus>('WAITING');
 const [lastEventTs,setLastEventTs]=useState(0);const [error,setError]=useState('');
 const state=useFlowStore();
 useEffect(()=>{
  let alive=true,subscribed=false,lastFrame=Date.now();
  flowStore.reset(market,symbol);
  const socket=io(process.env.NEXT_PUBLIC_SOCKET_URL,{path:'/socket.io',transports:['websocket'],reconnectionDelay:1000,reconnectionDelayMax:30000});
  const selection={market,symbol};
  socket.on('connect',()=>{
   setConnection('WAITING');setError('');subscribed=false;
   socket.timeout(15000).emit('flow_subscribe',selection,(failure:Error|null,ack:{success:boolean;market:Market;symbol:string;error?:string})=>{
    if(!alive)return;
    if(failure||!ack?.success||ack.market!==market||ack.symbol!==symbol){setError(ack?.error||'Stream subscription unavailable');setConnection('DISCONNECTED');return;}
    subscribed=true;void flowStore.hydrate(market,symbol);
   });
  });
  socket.on('disconnect',()=>{if(alive){subscribed=false;setConnection('DISCONNECTED');flowStore.reset(market,symbol);}});
  socket.on('connect_error',()=>{if(alive){setConnection('DISCONNECTED');setError('Stream disconnected');}});
  socket.on('flow:error',(data:{error?:string})=>{if(alive)setError(data.error||'Stream unavailable');});
  for(const type of ['tape','dom','footprint','heatmap','metrics','health']) socket.on(`flow:${type}`,data=>{
   if(!alive||!subscribed||data.market!==market||data.symbol!==symbol)return;
   lastFrame=Date.now();setLastEventTs(lastFrame);flowStore.dispatch({type:type.toUpperCase(),payload:data});
   if(type==='health')setConnection(data.status);
  });
  const polling=setInterval(()=>{if(subscribed)void flowStore.hydrate(market,symbol);},5000);
  const stale=setInterval(()=>{if(subscribed&&Date.now()-lastFrame>15000)setConnection('STALE');},1000);
  return ()=>{alive=false;clearInterval(polling);clearInterval(stale);socket.emit('flow_unsubscribe',selection);socket.removeAllListeners();socket.disconnect();flowStore.reset(market,symbol);};
 },[market,symbol]);
 const current=state.market===market&&state.symbol===symbol;
 return {status:connection==='STALE'||connection==='DISCONNECTED'?connection:current?state.health?.status||connection:'WAITING',lastEventTs,error};
}
