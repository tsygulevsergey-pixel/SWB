import asyncio
import logging
from typing import Dict, List, Optional
import time
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

logger = logging.getLogger(__name__)


class PairClustering:
    
    def __init__(self, config, cache, data_provider):
        self.config = config
        self.cache = cache
        self.data_provider = data_provider
        
        self._clusters: Dict[str, int] = {}
        self._cluster_positions: Dict[int, List[str]] = {}
        self._correlation_matrix: Dict[str, Dict[str, float]] = {}
        
        self._leader_symbols = config.cluster_leaders
        
        self._update_task = None
        self._running = False
    
    async def start(self, recalc_hour: int = 0):
        self._running = True
        self._update_task = asyncio.create_task(
            self._update_loop(recalc_hour)
        )
        logger.info(f"Pair clustering started (recalc at {recalc_hour}:00)")
    
    async def stop(self):
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info("Pair clustering stopped")
    
    async def _update_loop(self, recalc_hour: int):
        while self._running:
            try:
                await self.recalculate_clusters()
                
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in clustering update loop: {e}")
                await asyncio.sleep(600)
    
    async def recalculate_clusters(self):
        try:
            symbols = self.cache.candles.get_symbols_with_data()
            
            if len(symbols) < 10:
                logger.warning("Not enough symbols for clustering")
                return
            
            correlation_matrix = await self._calculate_correlations(symbols)
            
            self._correlation_matrix = correlation_matrix
            
            clusters = self._perform_clustering(symbols, correlation_matrix)
            
            self._clusters = clusters
            
            self._cluster_positions = {}
            for symbol, cluster_id in clusters.items():
                if cluster_id not in self._cluster_positions:
                    self._cluster_positions[cluster_id] = []
                self._cluster_positions[cluster_id].append(symbol)
            
            logger.info(f"Recalculated clusters: {len(set(clusters.values()))} clusters for {len(symbols)} symbols")
        
        except Exception as e:
            logger.error(f"Error recalculating clusters: {e}")
    
    async def _calculate_correlations(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        correlation_matrix = {}
        
        returns_data = {}
        
        for symbol in symbols[:100]:
            candles = self.cache.candles.get_candles(symbol, limit=200)
            
            if len(candles) < 50:
                continue
            
            closes = [c['close'] for c in candles[-50:]]
            
            returns = []
            for i in range(1, len(closes)):
                ret = (closes[i] - closes[i-1]) / closes[i-1]
                returns.append(ret)
            
            if returns:
                returns_data[symbol] = returns
        
        for sym1 in returns_data:
            correlation_matrix[sym1] = {}
            for sym2 in returns_data:
                if sym1 == sym2:
                    correlation_matrix[sym1][sym2] = 1.0
                else:
                    corr = np.corrcoef(returns_data[sym1], returns_data[sym2])[0, 1]
                    
                    if np.isnan(corr):
                        corr = 0.0
                    
                    correlation_matrix[sym1][sym2] = corr
        
        return correlation_matrix
    
    def _perform_clustering(self, symbols: List[str], correlation_matrix: Dict[str, Dict[str, float]]) -> Dict[str, int]:
        symbols_in_matrix = [s for s in symbols if s in correlation_matrix]
        
        if len(symbols_in_matrix) < 3:
            return {s: 0 for s in symbols_in_matrix}
        
        distance_matrix = []
        for sym1 in symbols_in_matrix:
            row = []
            for sym2 in symbols_in_matrix:
                corr = correlation_matrix[sym1].get(sym2, 0)
                distance = 1 - abs(corr)
                row.append(distance)
            distance_matrix.append(row)
        
        distance_matrix = np.array(distance_matrix)
        
        condensed_distance = squareform(distance_matrix)
        
        linkage_matrix = linkage(condensed_distance, method='ward')
        
        max_clusters = min(20, len(symbols_in_matrix) // 5)
        max_clusters = max(max_clusters, 3)
        
        cluster_labels = fcluster(linkage_matrix, max_clusters, criterion='maxclust')
        
        clusters = {}
        for i, symbol in enumerate(symbols_in_matrix):
            clusters[symbol] = int(cluster_labels[i])
        
        return clusters
    
    def get_cluster_id(self, symbol: str) -> Optional[int]:
        return self._clusters.get(symbol)
    
    def get_cluster_positions(self, cluster_id: int) -> List[str]:
        return self._cluster_positions.get(cluster_id, [])
    
    def get_symbol_cluster_load(self, symbol: str) -> int:
        cluster_id = self.get_cluster_id(symbol)
        
        if cluster_id is None:
            return 0
        
        positions = self.get_cluster_positions(cluster_id)
        return len(positions)
    
    def can_add_position_to_cluster(self, symbol: str) -> bool:
        cluster_id = self.get_cluster_id(symbol)
        
        if cluster_id is None:
            return True
        
        current_positions = len(self.get_cluster_positions(cluster_id))
        
        return current_positions < self.config.cluster_max_positions
    
    def get_correlation_with_leaders(self, symbol: str) -> float:
        if symbol not in self._correlation_matrix:
            return 0.0
        
        correlations = []
        for leader in self._leader_symbols:
            if leader in self._correlation_matrix[symbol]:
                corr = abs(self._correlation_matrix[symbol][leader])
                correlations.append(corr)
        
        if correlations:
            return max(correlations)
        
        return 0.0
    
    def is_leader_symbol(self, symbol: str) -> bool:
        return symbol in self._leader_symbols
    
    def get_cluster_penalty(self, symbol: str) -> float:
        if not self.can_add_position_to_cluster(symbol):
            return 10.0
        
        cluster_load = self.get_symbol_cluster_load(symbol)
        
        penalty = (cluster_load / self.config.cluster_max_positions) * 5.0
        
        return penalty
