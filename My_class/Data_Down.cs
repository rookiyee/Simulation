using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Clairvoyance.My_class
{
    class Data_Down : IDisposable
    {
        private string Down_Path;
        private StreamWriter? sw;

        /// <summary>
        /// K_name 為刀把名稱
        /// K_onTim 為物件建立時間
        /// </summary>
        public Data_Down(string K_name, string K_onTim)
        {
            this.Down_Path = $"./User_TTCdata/{K_name}/{K_onTim}.csv";
            Init();
        }

        private void Init()
        {
            // 取得資料夾路徑
            string folderPath = Path.GetDirectoryName(Down_Path)!;

            // 確保資料夾存在
            Directory.CreateDirectory(folderPath);

            // 建立 StreamWriter，若檔案不存在會自動建立
            sw = new StreamWriter(Down_Path, append: true, encoding: new UTF8Encoding(false));
        }

        /// <summary>
        /// 將字串寫入檔案（同步，附加於檔案尾）
        /// </summary>
        public void Write(string content)
        {
            if (sw == null) return;

            sw.Write(content);
            sw.Flush(); // 確保資料即時寫入磁碟（避免快取延遲）
        }

        /// <summary>
        /// 結束使用後釋放資源
        /// </summary>
        public void Dispose()
        {
            sw?.Dispose();
            sw = null!;
        }
    }
}