using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Text.RegularExpressions;
using System.Net.Sockets;
using System.Threading;
using DocumentFormat.OpenXml.Drawing;
using static System.Diagnostics.Debugger;
using System.Collections.Concurrent;
using System.IO;
using Avalonia.Controls;

namespace Clairvoyance.My_class
{
    public class TTC_Link_TCP
    {
        #region 參數宣告

        #region 刀把連線相關參數

        private string K_IP; // 刀把連線的 IP

        private int K_Port; // 刀把傳輸的 Port

        private int K_Count; // 刀把每組資料的封包長度

        private int K_Ch; // 通道數量 

        private Socket TCPLInk; // TCP 網路連接 客戶端

        #endregion

        #region 執行續規劃與內存管理參數

        private Task Tk_read; // TCP 讀取執行續

        private Task Tk_treat; // 接收解碼，執行續

        // 取消令牌源，用於優雅地停止所有異步任務
        private CancellationTokenSource CTS_stopToken;

        // 先進先出 buffer 用來儲存 esp866ex 傳給刀把的原始資料
        private BlockingCollection<byte[]> FIFO_BufLst;

        private List<double[]> AD7606_VarLstArF64;

        #endregion

        #endregion

        #region 初始化函數

        public TTC_Link_TCP(string K_IP) 
        {
            this.K_IP = K_IP;
            this.K_Port = 4321;
            this.K_Count = 14 ; // 標頭(1) + 4通道壓電(8) + ADC主板電壓(2) + 電池電壓(2) + 標尾(1) 
            this.K_Ch = (K_Count-2) / 2 ; // 每組資料都為 2Byte 所以除2，

            Init();
        }

        public void Init()
        {
            #region TCP 連線初始化

            FIFO_BufLst = new BlockingCollection<byte[]>(new ConcurrentQueue<byte[]>());
            CTS_stopToken = new CancellationTokenSource();

            #endregion


            AD7606_VarLstArF64 = new List<double[]>();

            Start();
        }

        /// <summary>
        /// 因為每次的斷線 Socket 實例的內部狀態會變成已關閉 (Disposed)，所以 Socket 需要頻繁的清除
        /// </summary>
        private void Init_TCPLInk()
        {
            // 若舊的 socket 存在，就先關閉
            if (TCPLInk != null)
            {
                try { TCPLInk.Close(); } catch { }
            }

            TCPLInk = new Socket(
                AddressFamily.InterNetwork, // 位址通訊互聯網使用 IPV4 對 IP 地址通訊
                SocketType.Stream,
                ProtocolType.Tcp // TCP 通訊
                );

            // 1. 禁用 Nagle 演算法：避免封包合併延遲
            TCPLInk.NoDelay = true;

            // 2. 設定接收緩衝區大小（ 256~512 KB）
            TCPLInk.ReceiveBufferSize = 262144; // 計算目前 10kHZ 15Byte 約可存 1.5s 的刀把傳送資料

            // 3. 設定傳送緩衝區（若之後也要回傳資料）
            TCPLInk.SendBufferSize = 65536; // 預設已夠，但可保守設大一點

            // 4. 設定接收超時（可選）
            TCPLInk.ReceiveTimeout = 1000; // 1 秒內未收到會拋例外（配合監控重連）

            // 5. 設定 KeepAlive（可選）解決 ESP8266 停止傳資料或斷線時 PC 不知道的問題
            TCPLInk.SetSocketOption(
                SocketOptionLevel.Socket,
                SocketOptionName.KeepAlive, true // 開啟 TCP 自動探測是否還連線
                );

            // 6. 
            TCPLInk.SetSocketOption(SocketOptionLevel.Tcp, SocketOptionName.NoDelay, true);
        }

        #endregion

        #region 使用函數

        /// <summary>
        /// 開始讀取刀把函數
        /// </summary>
        public void Start()
        {
            // 初始化 TCP 客戶端
            Init_TCPLInk();

            // 裝載 異步任務進入 Task
            Tk_read = Task.Run(Tk_read_ff);
            Tk_treat = Task.Run(Tk_treat_ff);
        }

        private readonly object _lifeLock = new();
        /// <summary>
        /// 斷開 TCP 連線並清理所有背景執行緒/資源。
        /// fastRelease = true 時，使用 Linger(0) 送 RST，立即釋放本機埠。
        /// </summary>
        public void Disconnect(bool fastRelease = true, int joinTimeoutSec = 2)
        {
            Task? tRead = null;
            Task? tTreat = null;
            Socket? sock = null;
            BlockingCollection<byte[]>? fifo = null;
            CancellationTokenSource? cts = null;

            lock (_lifeLock)
            { 

                // 發送取消信號
                cts = CTS_stopToken;
                CTS_stopToken = null;
                cts?.Cancel();

                // 取出背景任務 & socket & 佇列
                tRead = Tk_read; Tk_read = null;
                tTreat = Tk_treat; Tk_treat = null;

                sock = TCPLInk; TCPLInk = null;
                fifo = FIFO_BufLst; FIFO_BufLst = null;
            }

            try
            {
                // 關閉 Socket：Shutdown → (選) Linger(0) → Close/Dispose
                if (sock != null)
                {
                    try
                    {
                        try { sock.Shutdown(SocketShutdown.Both); } catch { /* ignore */ }
                        if (fastRelease)
                        {
                            // 送 RST 讓 TIME_WAIT 最小化，盡快釋放埠
                            sock.LingerState = new LingerOption(true, 0);
                        }
                        sock.Close();   // 會隱含 Dispose
                        sock.Dispose();
                    }
                    catch { /* ignore */ }
                }

                // 同步等待背景任務結束（逾時避免卡死 UI）
                var waitList = new[] { tRead, tTreat }.Where(t => t != null)!.Cast<Task>().ToArray();
                if (waitList.Length > 0)
                {
                    try
                    {
                        var all = Task.WhenAll(waitList);
                        if (!all.Wait(TimeSpan.FromSeconds(joinTimeoutSec)))
                        {
                            Console.WriteLine("⚠️ 背景任務停止逾時，已略過。");
                        }
                    }
                    catch (AggregateException)
                    {
                        // 多半是取消/Socket 關閉引發，這裡吞掉即可
                    }
                }

                // 清理佇列
                if (fifo != null)
                {
                    try { fifo.CompleteAdding(); } catch { }
                    try { while (fifo.TryTake(out _, 0)) { } } catch { }
                    try { fifo.Dispose(); } catch { }
                }
            }
            finally
            {
                try { cts?.Dispose(); } catch { }
            }

            Console.WriteLine("🔧 TCP 連線與資源已完整清理，埠已釋放。");
        }

        /// <summary>
        /// 將資料整粒給 UI 畫畫用的
        /// ⚠️<b> 注意 :『每次讀取都會清空』</b>
        /// </summary>
        /// 原本 List array 後 double 的方式儲存是為了，方變儲存和儲存用的
        /// 因為資料是，AD7606的資料是一筆一筆寫入的，所以一組組儲存方便，
        /// 速度不一定快但一定安全，且不會出現執行續混亂的問題。
        /// 但是要回傳給使用者(我或者下一個在 UI 上面畫畫的人)，讀到的數據用用來畫圖
        /// 資料最好是一個通道連續性，不是一個時間所有通道，所以還須最資料的轉換
        public List<double>[] GetArLstF64()
        {
            if (AD7606_VarLstArF64 == null || AD7606_VarLstArF64.Count < 5)
                return null;

            List<double>[] re = new List<double>[this.K_Ch];

            // 初始化每個 List   
            for (int i = 0; i < re.Length; i++)
            {
                re[i] = new List<double>();
            }

            // 深層 copy 這樣，只是複製資料而已
            List<double[]> Copy_data = AD7606_VarLstArF64
                .Select(arr => arr.ToArray()) // 複製每個 double[]
                .ToList();                     // 複製整個 List

            // 意思就是轉至
            foreach (var arr in Copy_data)
            {
                for (int i = 0; i < arr.Length; i++)
                {
                    re[i].Add(arr[i]);
                }
            }

            // 清空內存
            AD7606_VarLstArF64 = new List<double[]>();

            return re ;
        }

        /// <summary>
        /// 接收資料異步函數
        /// </summary>
        private void Tk_read_ff()
        {
            try
            {
                TCPLInk.Connect(K_IP,K_Port);
            }
            catch ( Exception e )
            { 
               // Break(); // 有問題就抱錯啊!不然勒
            }

            while (CTS_stopToken != null && FIFO_BufLst!=null && !CTS_stopToken.Token.IsCancellationRequested)
            {
                try
                {
                    byte[] buffer = new byte[4096];
                    int len = TCPLInk.Receive(buffer);

                    if (len > 0)
                    {
                        byte[] data = new byte[len];
                        Array.Copy(buffer, data, len);
                        try
                        {
                            FIFO_BufLst.Add(data);
                        }
                        catch
                        {
                            return;
                        }
                        
                    }
                    else
                    {
                        // 🔥 收到 0 bytes 表示連線關閉
                        Console.WriteLine("📡 TCP 連線已關閉");
                        break;
                    }
                }
                catch (SocketException)
                {
                    // 🔥 Socket 錯誤通常表示連線中斷
                    Console.WriteLine("🔌 Socket 連線中斷");
                    break;
                }
                catch (ObjectDisposedException)
                {
                    // 🔥 Socket 已被釋放
                    Console.WriteLine("🗑️ Socket 已釋放");
                    break;
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"❌ 接收資料錯誤: {ex.Message}");
                    break;
                }
            }
        }

        /// <summary>
        /// 解析資料異步函數 - 修正版
        /// </summary>
        private void Tk_treat_ff()
        {
            List<byte> rew_data = new List<byte>();
            int processed_index = 0; // 添加處理位置記錄
            int data_long = K_Count - 2; // 資料長度為封包長度減標頭標尾
            const int MAX_BUFFER_SIZE = 1024 * 1024; // 1MB 緩衝區限制

            while (CTS_stopToken!= null && !CTS_stopToken.Token.IsCancellationRequested)
            {
                try
                {
                    // 讀取緩衝裡面的資料
                    byte[] data = FIFO_BufLst.Take(CTS_stopToken.Token);

                    // 以陣列轉List避免記憶體不完整
                    rew_data.AddRange(data);

                    // 定期清理緩衝區，防止記憶體溢出
                    if (rew_data.Count > MAX_BUFFER_SIZE)
                    {
                        // 保留未處理的資料
                        if (processed_index < rew_data.Count)
                        {
                            List<byte> remaining_data = rew_data.GetRange(processed_index,
                                rew_data.Count - processed_index);
                            rew_data.Clear();
                            rew_data.AddRange(remaining_data);
                            processed_index = 0;
                        }
                        else
                        {
                            rew_data.Clear();
                            processed_index = 0;
                        }
                    }

                    // 從上次處理的位置繼續
                    int i = processed_index;

                    // 確保有足夠的資料進行完整封包檢查
                    while (i <= rew_data.Count - (data_long + 2))
                    {
                        // 檢查封包標頭和標尾
                        if (rew_data[i] == 0xAA && rew_data[i + data_long + 1] == 0xBB)
                        {
                            // 提取封包資料（排除標頭標尾）
                            byte[] packet = rew_data.GetRange(i + 1, data_long).ToArray();

                            try
                            {
                                AD7606_VarLstArF64_Add(packet);
                            }
                            catch (Exception ex)
                            {
                                // 記錄錯誤但繼續處理，不中斷整個流程
                                // 可以添加日誌記錄
                                System.Diagnostics.Debug.WriteLine($"封包處理錯誤: {ex.Message}");
                            }

                            // 跳過整個封包
                            i += data_long + 2;
                        }
                        else
                        {
                            // 沒找到有效封包，繼續下一個位置
                            i++;
                        }
                    }

                    // 更新處理位置
                    processed_index = i;
                }
                catch (OperationCanceledException)
                {
                    // 正常取消，退出循環
                    break;
                }
                catch (Exception ex)
                {
                    // 其他錯誤，記錄但不中斷
                    System.Diagnostics.Debug.WriteLine($"資料處理錯誤: {ex.Message}");
                    continue;
                }
            }
        }

        /// <summary>
        /// 處理 AD7606_VarLstArF64 的內存管理
        /// </summary>
        private void AD7606_VarLstArF64_Add(byte[] packet)
        {
            // 通道數量阿! 不然勒
            double [] dvar = new double[this.K_Ch];
            ushort[] raw_data = new ushort[this.K_Ch];

            for(int i = 0, i_packet = 0; i < this.K_Ch; i_packet = ++i * 2)
            {
                raw_data[i] = (ushort)( (packet[i_packet] << 8) | packet[i_packet + 1]);
                dvar[i] = AD7606ConvValue(raw_data[i]);
            }

            // 資料要先被安全儲存，才加入內存
            

            // 將資料儲存至內存
            AD7606_VarLstArF64.Add(dvar);
        }


        /// <summary>
        /// AD7606 ADC數值轉換函數
        /// 將16位元二進位補數轉換為電壓值（±5V範圍）
        /// </summary>
        /// <param name="bin">16位元無符號整數</param>
        /// <returns>轉換後的電壓值</returns>
        private double AD7606ConvValue(ushort bin)
        {

            // 1. 正確的二補數轉換 (16位元)
            // 將 ushort 直接轉換為 short，C# 會自動處理符號位
            short signedVal = (short)bin;

            // 2. 根據 ±5V 範圍進行縮放
            // AD7606 的 ±5V 範圍對應二補數的 -32768 到 +32767
            // 因此，將 signedVal (-32768 ~ +32767) 映射到 -5.0V ~ +5.0V
            return (signedVal * 5.0) / 32768.0;

        }

        #endregion
    }
}
