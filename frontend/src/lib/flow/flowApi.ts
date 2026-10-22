import { request, Market } from '../market';
import type { StreamHealth, FootprintBar, TapeEntry, DomAnalytics, HeatmapSnapshot, VolumeProfileSnapshot, FlowMetrics, CVDPoint } from './flowTypes';
export interface FlowStatusResponse {enabled:boolean;reason?:string;symbols?:string[];health?:Record<string,StreamHealth>}
export interface FootprintResponse {market:Market;symbol:string;interval:string;tick_group:number;bars:FootprintBar[]}
async function read<T>(path:string,market:Market,symbol?:string,params:Record<string,string|number|undefined>={},signal?:AbortSignal):Promise<T|null>{
 const query=new URLSearchParams({market,...(symbol?{symbol}:{})});
 for(const [key,value] of Object.entries(params))if(value!==undefined)query.set(key,String(value));
 try{return await request<T>(`/api/flow/${path}?${query}`,{signal});}catch{return null;}
}
export const getFlowStatus=(market:Market='spot')=>read<FlowStatusResponse>('status',market);
export const getFootprint=(symbol:string,interval='1m',limit=60,tick_group?:number,market:Market='spot',signal?:AbortSignal)=>read<FootprintResponse>('footprint',market,symbol,{interval,limit,tick_group},signal);
export const getDom=(symbol:string,levels=20,tick_group?:number,market:Market='spot',signal?:AbortSignal)=>read<DomAnalytics>('dom',market,symbol,{levels,tick_group},signal);
export const getTape=(symbol:string,limit=200,min_notional?:number,market:Market='spot',signal?:AbortSignal)=>read<{symbol:string;market:Market;entries:TapeEntry[]}>('tape',market,symbol,{limit,min_notional},signal);
export const getHeatmap=(symbol:string,window_sec?:number,tick_group?:number,market:Market='spot',signal?:AbortSignal)=>read<HeatmapSnapshot>('heatmap',market,symbol,{window_sec,tick_group},signal);
export const getVolumeProfile=(symbol:string,mode:'SESSION'|'VISIBLE'|'FIXED_RANGE'='SESSION',start_ts?:number,end_ts?:number,tick_group?:number,market:Market='spot',signal?:AbortSignal)=>read<VolumeProfileSnapshot>('volume-profile',market,symbol,{mode,start_ts,end_ts,tick_group},signal);
export const getCVD=(symbol:string,interval='1m',limit=240,market:Market='spot',signal?:AbortSignal)=>read<{symbol:string;points:CVDPoint[];vwap:number;vwap_upper_1:number;vwap_lower_1:number}>('cvd',market,symbol,{interval,limit},signal);
export const getMetrics=(symbol:string,market:Market='spot',signal?:AbortSignal)=>read<FlowMetrics>('metrics',market,symbol,{},signal);
export const getSymbolInfo=(symbol:string,market:Market='spot')=>read<Record<string,unknown>>('symbol-info',market,symbol);
