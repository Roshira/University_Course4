-- | Обмінне сортування зі злиттям Бетчера (odd-even merge sort)
--   з розпаралелюванням кожного етапу сортувальної мережі на k потоків.
module Batcher
  ( stages
  , comparatorsOf
  , sortSeq
  , sortPar
  , sortListPar
  ) where

import Control.Concurrent (forkOn, getNumCapabilities)
import Control.Concurrent.MVar
import Control.Exception (SomeException, evaluate, try, throwIO)
import Control.Monad (forM, forM_, when)
import Data.Array.Base (unsafeRead, unsafeWrite)
import Data.Array.IO (IOUArray, getElems, newListArray)
import Data.Bits (shiftL, shiftR, (.&.))

-- | Етапи мережі Бетчера для n елементів: пари (p, k).
--   Усі компаратори одного етапу не перетинаються, тож етап можна
--   виконувати паралельно, а між етапами потрібна синхронізація (бар'єр).
stages :: Int -> [(Int, Int)]
stages n =
  [ (p, k)
  | p <- takeWhile (< n) (iterate (`shiftL` 1) 1)
  , k <- takeWhile (>= 1) (iterate (`shiftR` 1) p)
  ]

-- | Чи починається в позиції a компаратор (a, a+k) на етапі (p, k).
isComparator :: Int -> Int -> Int -> Int -> Bool
isComparator n p k a =
  let r  = k .&. (p - 1)          -- k mod p (p — степінь двійки)
      p2 = 2 * p
  in  a >= r
      && ((a - r) `rem` (2 * k)) < k
      && a + k < n
      && a `quot` p2 == (a + k) `quot` p2
{-# INLINE isComparator #-}

-- | Список компараторів етапу (для тестів і наочності).
comparatorsOf :: Int -> (Int, Int) -> [(Int, Int)]
comparatorsOf n (p, k) = [ (a, a + k) | a <- [0 .. n - k - 1], isComparator n p k a ]

-- | Виконати компаратори етапу (p, k), що починаються в позиціях [lo, hi).
runRange :: IOUArray Int Int -> Int -> Int -> Int -> Int -> Int -> IO ()
runRange arr n p k lo hi = go lo
  where
    go :: Int -> IO ()
    go a
      | a >= hi = pure ()
      | isComparator n p k a = do
          x <- unsafeRead arr a
          y <- unsafeRead arr (a + k)
          when (x > y) $ unsafeWrite arr a y >> unsafeWrite arr (a + k) x
          go (a + 1)
      | otherwise = go (a + 1)

-- | Послідовна версія (один потік) — еталон для порівняння часу.
sortSeq :: IOUArray Int Int -> Int -> IO ()
sortSeq arr n = forM_ (stages n) $ \(p, k) -> runRange arr n p k 0 (n - k)

-- | Паралельна версія: k робочих потоків, кожен етап ділиться на k
--   рівних частин; після етапу — бар'єр (очікування всіх потоків).
sortPar :: Int -> IOUArray Int Int -> Int -> IO ()
sortPar threads arr n
  | threads <= 1 = sortSeq arr n
  | otherwise = do
      caps <- getNumCapabilities
      forM_ (stages n) $ \(p, k) -> do
        let m      = n - k
            chunk  = (m + threads - 1) `div` threads
            ranges = [ (lo, min m (lo + chunk)) | lo <- [0, chunk .. m - 1] ]
        dones <- forM (zip [0 ..] ranges) $ \(t, (lo, hi)) -> do
          done <- newEmptyMVar
          _ <- forkOn (t `mod` caps) $
                 try (runRange arr n p k lo hi) >>= putMVar done
          pure done
        forM_ dones $ \d -> takeMVar d >>= either rethrow pure
  where
    rethrow :: SomeException -> IO ()
    rethrow = throwIO

-- | Зручна обгортка: відсортувати список на k потоках.
sortListPar :: Int -> [Int] -> IO [Int]
sortListPar threads xs = do
  let n = length xs
  if n < 2
    then pure xs
    else do
      arr <- newListArray (0, n - 1) xs
      sortPar threads arr n
      ys <- getElems arr
      _ <- evaluate (sum ys)
      pure ys
